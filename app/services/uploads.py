"""
Upload seguro de arquivos (imagens do site, vídeo do hero).

Camadas de proteção aplicadas:
1. Extensão em whitelist (nunca aceita a extensão enviada "crua" sem checar).
2. Validação do conteúdo real do arquivo via "magic bytes" (python-magic),
   evitando que um .php renomeado para .jpg seja aceito.
3. Para imagens, reabre com Pillow (verify + re-save), o que também
   remove metadados/EXIF potencialmente maliciosos e garante que o
   arquivo é uma imagem válida e decodificável.
4. Nome de arquivo gerado com uuid4 (nunca usa o nome original do
   usuário), eliminando path traversal e colisões.
5. Tamanho máximo controlado por MAX_CONTENT_LENGTH (Flask) e checado
   novamente aqui por segurança.
"""
import io
import os
import uuid

from flask import current_app
from PIL import Image
from werkzeug.utils import secure_filename

try:
    import magic  # python-magic

    _HAS_MAGIC = True
except Exception:  # pragma: no cover - ambiente sem libmagic instalada
    _HAS_MAGIC = False

ALLOWED_IMAGE_MIME = {"image/jpeg", "image/png", "image/webp", "image/gif"}
ALLOWED_VIDEO_MIME = {"video/mp4", "video/webm"}


# Dimensão máxima (maior lado, em pixels) por tipo de imagem. Imagens maiores
# que isso são redimensionadas antes de salvar — reduz drasticamente o peso
# do arquivo sem perda perceptível de qualidade para uso web.
MAX_DIMENSIONS = {
    "content/services": (1200, 1200),
    "content/gallery": (1400, 1400),
    "content/partners": (600, 600),
    "content": (1400, 1400),
}
DEFAULT_MAX_DIMENSION = (1600, 1600)


class UploadError(Exception):
    pass


def _extension(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def _detect_mime(file_storage) -> str:
    head = file_storage.stream.read(2048)
    file_storage.stream.seek(0)
    if _HAS_MAGIC:
        return magic.from_buffer(head, mime=True)
    # Fallback sem libmagic: usa o content-type informado pelo cliente
    # (menos confiável, por isso libmagic é fortemente recomendada em produção).
    return file_storage.mimetype or "application/octet-stream"


def save_image(file_storage, subfolder: str = "content") -> str:
    """
    Valida, otimiza e salva uma imagem enviada, retornando o caminho
    relativo (ex.: "uploads/content/ab12cd34.webp") para ser guardado no banco.

    Otimizações aplicadas automaticamente:
    - Redimensionamento para o tamanho máximo adequado ao contexto de uso
      (logo de parceiro não precisa da mesma resolução de uma foto de galeria).
    - Conversão para WEBP com qualidade 82 (ótimo custo/benefício tamanho x
      qualidade para uso web).
    - Remoção de metadados/EXIF (também reduz o tamanho do arquivo).
    """
    if not file_storage or not file_storage.filename:
        raise UploadError("Nenhum arquivo enviado.")

    ext = _extension(secure_filename(file_storage.filename))
    allowed_ext = current_app.config["ALLOWED_IMAGE_EXTENSIONS"]
    if ext not in allowed_ext:
        raise UploadError(f"Extensão .{ext} não permitida. Use: {', '.join(sorted(allowed_ext))}.")

    mime = _detect_mime(file_storage)
    if mime not in ALLOWED_IMAGE_MIME:
        raise UploadError("O conteúdo do arquivo não corresponde a uma imagem válida.")

    raw_bytes = file_storage.read()
    if len(raw_bytes) == 0:
        raise UploadError("Arquivo vazio.")
    if len(raw_bytes) > current_app.config["MAX_CONTENT_LENGTH"]:
        raise UploadError("Arquivo excede o tamanho máximo permitido.")

    # Revalida com Pillow: garante que é uma imagem decodificável e
    # descarta metadados potencialmente perigosos ao regravar do zero.
    try:
        image = Image.open(io.BytesIO(raw_bytes))
        image.verify()
        image = Image.open(io.BytesIO(raw_bytes))  # verify() invalida o objeto; reabrir
        if image.mode == "CMYK":
            image = image.convert("RGB")
        elif image.mode == "P":
            image = image.convert("RGBA") if "transparency" in image.info else image.convert("RGB")
    except Exception as exc:  # noqa: BLE001
        raise UploadError("Não foi possível processar a imagem enviada.") from exc

    # Redimensiona preservando o aspect ratio, apenas se a imagem for maior
    # que o necessário (nunca amplia imagens pequenas).
    max_size = MAX_DIMENSIONS.get(subfolder, DEFAULT_MAX_DIMENSION)
    image.thumbnail(max_size, Image.LANCZOS)

    upload_root = current_app.config["UPLOAD_FOLDER"]
    target_dir = os.path.join(upload_root, subfolder)
    os.makedirs(target_dir, exist_ok=True)

    filename = f"{uuid.uuid4().hex}.webp"
    absolute_path = os.path.join(target_dir, filename)
    image.save(absolute_path, format="WEBP", quality=82, method=6)

    return f"uploads/{subfolder}/{filename}"


def save_video(file_storage, subfolder: str = "hero") -> str:
    """Valida (extensão + mime) e salva um vídeo, sem reprocessamento de conteúdo."""
    if not file_storage or not file_storage.filename:
        raise UploadError("Nenhum arquivo enviado.")

    ext = _extension(secure_filename(file_storage.filename))
    allowed_ext = current_app.config["ALLOWED_VIDEO_EXTENSIONS"]
    if ext not in allowed_ext:
        raise UploadError(f"Extensão .{ext} não permitida. Use: {', '.join(sorted(allowed_ext))}.")

    mime = _detect_mime(file_storage)
    if mime not in ALLOWED_VIDEO_MIME:
        raise UploadError("O conteúdo do arquivo não corresponde a um vídeo válido.")

    file_storage.stream.seek(0, os.SEEK_END)
    size = file_storage.stream.tell()
    file_storage.stream.seek(0)
    if size > current_app.config["MAX_CONTENT_LENGTH"]:
        raise UploadError("Arquivo excede o tamanho máximo permitido.")

    upload_root = current_app.config["UPLOAD_FOLDER"]
    target_dir = os.path.join(upload_root, subfolder)
    os.makedirs(target_dir, exist_ok=True)

    filename = f"{uuid.uuid4().hex}.{ext}"
    absolute_path = os.path.join(target_dir, filename)
    file_storage.save(absolute_path)

    return f"uploads/{subfolder}/{filename}"


def delete_upload(relative_path: str) -> None:
    """Remove um arquivo previamente enviado, ignorando se já não existir."""
    if not relative_path:
        return
    upload_root = current_app.config["UPLOAD_FOLDER"]
    # relative_path já vem no formato "uploads/xxx/arquivo.ext"
    root_parent = os.path.dirname(upload_root)
    absolute_path = os.path.join(root_parent, relative_path)
    try:
        if os.path.isfile(absolute_path):
            os.remove(absolute_path)
    except OSError:
        current_app.logger.warning("Falha ao remover arquivo de upload: %s", relative_path)
