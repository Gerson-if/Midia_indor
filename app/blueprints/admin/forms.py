from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField
from wtforms import (
    BooleanField,
    FloatField,
    IntegerField,
    PasswordField,
    RadioField,
    SelectField,
    StringField,
    TextAreaField,
)
from wtforms.validators import DataRequired, Email, Length, NumberRange, Optional, Regexp

# Aceita hexadecimal de 6 dígitos com # (ex.: #FFB020) — é o formato que o
# próprio <input type="color"> do navegador sempre envia, e também o que
# esperamos quando o admin digita/cola um hex manualmente no campo de
# texto pareado. Validar no servidor (além do JS) evita que um valor fora
# do padrão (ou malicioso, tipo "red;background:url(...)") seja salvo e
# injetado depois dentro de atributos style="" nos templates públicos.
HEX_COLOR_RE = Regexp(r"^#[0-9a-fA-F]{6}$", message="Use um hexadecimal válido, ex.: #FFB020.")

from app.models.proposal import ProposalStatus


class ProposalStatusForm(FlaskForm):
    status = SelectField(
        "Status",
        choices=[(s.value, s.value) for s in ProposalStatus],
        validators=[DataRequired()],
    )
    internal_notes = TextAreaField("Notas internas", validators=[Optional(), Length(max=2000)])
    version_id = IntegerField("version", validators=[Optional()])


class ServiceForm(FlaskForm):
    # display_order não é mais um campo do formulário: itens novos entram
    # automaticamente no final da lista, e a reordenação passou a ser feita
    # arrastando os cards (ver admin.services_reorder), não digitando um
    # número — mais rápido e sem risco de dois itens ficarem com a mesma
    # posição por engano.
    title = StringField("Título", validators=[DataRequired(), Length(max=120)])
    description = TextAreaField("Descrição", validators=[DataRequired(), Length(max=400)])
    is_active = BooleanField("Ativo", default=True)
    image = FileField("Imagem", validators=[Optional(), FileAllowed(["jpg", "jpeg", "png", "webp", "gif"])])
    remove_image = BooleanField("Remover imagem atual")


class GalleryItemForm(FlaskForm):
    title = StringField("Título", validators=[DataRequired(), Length(max=120)])
    category = StringField("Categoria", validators=[DataRequired(), Length(max=80)])
    is_active = BooleanField("Ativo", default=True)
    image = FileField("Imagem", validators=[Optional(), FileAllowed(["jpg", "jpeg", "png", "webp", "gif"])])
    remove_image = BooleanField("Remover imagem atual")


class CustomSectionForm(FlaskForm):
    nav_label = StringField("Nome no menu", validators=[DataRequired(), Length(max=60)])
    heading = StringField("Título da seção", validators=[DataRequired(), Length(max=150)])
    subtitle = TextAreaField("Descrição (opcional)", validators=[Optional(), Length(max=300)])
    is_active = BooleanField("Ativa (visível no site)", default=True)


class CustomSectionItemForm(FlaskForm):
    title = StringField("Título", validators=[DataRequired(), Length(max=120)])
    description = TextAreaField("Descrição", validators=[Optional(), Length(max=400)])
    is_active = BooleanField("Ativo", default=True)
    image = FileField("Imagem", validators=[Optional(), FileAllowed(["jpg", "jpeg", "png", "webp", "gif"])])
    remove_image = BooleanField("Remover imagem atual")


class TestimonialForm(FlaskForm):
    name = StringField("Nome", validators=[DataRequired(), Length(max=120)])
    company_name = StringField("Empresa", validators=[DataRequired(), Length(max=120)])
    text = TextAreaField("Depoimento", validators=[DataRequired(), Length(max=600)])
    is_active = BooleanField("Ativo", default=True)


class PartnerForm(FlaskForm):
    name = StringField("Nome da marca", validators=[DataRequired(), Length(max=120)])
    is_active = BooleanField("Ativo", default=True)
    logo = FileField("Logo", validators=[Optional(), FileAllowed(["jpg", "jpeg", "png", "webp", "gif"])])
    remove_logo = BooleanField("Remover logo atual")


class SiteSettingsForm(FlaskForm):
    company_name = StringField("Nome da empresa", validators=[DataRequired(), Length(max=120)])
    company_description = TextAreaField("Descrição", validators=[Optional(), Length(max=400)])
    company_whatsapp = StringField("WhatsApp (somente números, com DDI)", validators=[DataRequired(), Length(max=20)])
    whatsapp_default_message = TextAreaField(
        "Mensagem automática do botão \"Chamar no WhatsApp\"",
        validators=[Optional(), Length(max=300)],
    )
    company_email = StringField("E-mail", validators=[Optional(), Email(), Length(max=190)])
    company_phone = StringField("Telefone", validators=[Optional(), Length(max=30)])
    company_address = StringField("Endereço", validators=[Optional(), Length(max=255)])
    color_primary = StringField("Cor primária", validators=[DataRequired(), Length(max=9), HEX_COLOR_RE])
    color_secondary = StringField("Cor secundária", validators=[DataRequired(), Length(max=9), HEX_COLOR_RE])
    whatsapp_button_color = StringField(
        "Cor do botão do WhatsApp", validators=[DataRequired(), Length(max=9), HEX_COLOR_RE]
    )

    # ---- Identidade visual ----
    favicon = FileField(
        "Favicon (ícone da aba)",
        validators=[Optional(), FileAllowed(["png", "jpg", "jpeg", "ico", "webp"], "Envie um .png, .ico, .jpg ou .webp.")],
    )
    remove_favicon = BooleanField("Remover favicon atual")
    logo = FileField(
        "Logo da empresa",
        validators=[Optional(), FileAllowed(["jpg", "jpeg", "png", "webp", "gif"], "Envie uma imagem válida.")],
    )
    remove_logo = BooleanField("Remover logo atual")

    hero_title = StringField("Título do Hero", validators=[Optional(), Length(max=200)])
    hero_subtitle = TextAreaField("Subtítulo do Hero", validators=[Optional(), Length(max=400)])
    hero_media_type = RadioField(
        "Tipo de capa do Hero",
        choices=[("video", "Vídeo"), ("image", "Imagem estática")],
        validators=[DataRequired()],
    )
    hero_overlay_opacity = FloatField("Opacidade do overlay", validators=[Optional(), NumberRange(min=0, max=1)])
    hero_cta_primary_label = StringField("Texto do botão principal", validators=[Optional(), Length(max=80)])
    hero_cta_secondary_label = StringField("Texto do botão secundário", validators=[Optional(), Length(max=80)])
    hero_video = FileField("Vídeo de fundo", validators=[Optional(), FileAllowed(["mp4", "webm"], "Envie um arquivo .mp4 ou .webm.")])
    hero_image = FileField(
        "Imagem de capa",
        validators=[Optional(), FileAllowed(["jpg", "jpeg", "png", "webp", "gif"], "Envie uma imagem válida.")],
    )
    remove_hero_video = BooleanField("Remover vídeo atual")
    remove_hero_image = BooleanField("Remover imagem atual")

    # ---- Aparência das demais seções ----
    services_accent_color = StringField("Destaque — Vantagens", validators=[DataRequired(), Length(max=9), HEX_COLOR_RE])
    gallery_accent_color = StringField("Destaque — Galeria", validators=[DataRequired(), Length(max=9), HEX_COLOR_RE])
    testimonials_accent_color = StringField(
        "Destaque — Depoimentos", validators=[DataRequired(), Length(max=9), HEX_COLOR_RE]
    )
    card_background_color = StringField("Fundo dos cards", validators=[DataRequired(), Length(max=9), HEX_COLOR_RE])
    card_border_radius = IntegerField("Arredondamento dos cards (px)", validators=[Optional(), NumberRange(min=0, max=40)])
    theme = RadioField(
        "Tema do sistema",
        choices=[("dark", "Escuro"), ("light", "Claro")],
        validators=[DataRequired()],
    )

    # ---- Páginas legais ----
    privacy_content = TextAreaField("Conteúdo — Política de Privacidade", validators=[Optional(), Length(max=20000)])
    terms_content = TextAreaField("Conteúdo — Termos de Uso", validators=[Optional(), Length(max=20000)])

    version_id = IntegerField("version", validators=[Optional()])


class UserForm(FlaskForm):
    name = StringField("Nome", validators=[DataRequired(), Length(max=120)])
    email = StringField("E-mail", validators=[DataRequired(), Email(), Length(max=190)])
    role = SelectField("Papel", choices=[("admin", "Administrador"), ("editor", "Editor"), ("viewer", "Visualizador")])
    is_active = BooleanField("Ativo", default=True)
    password = PasswordField(
        "Senha (deixe em branco para manter a atual)",
        validators=[Optional(), Length(min=8, max=128)],
    )
