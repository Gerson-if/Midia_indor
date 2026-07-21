/**
 * Prévia instantânea de upload de mídia (imagem/vídeo) nos formulários do
 * painel admin, com opção de cancelar a seleção ANTES de salvar.
 *
 * Antes, a única forma de ver o arquivo enviado era salvar o formulário
 * (recarregando a página) — e não havia como desistir de um arquivo já
 * escolhido sem enviar outro no lugar ou concluir o salvamento. Este script
 * lê o arquivo escolhido no próprio navegador (sem round-trip ao servidor)
 * e mostra a prévia imediatamente, com um botão para cancelar a seleção e
 * voltar ao estado anterior (imagem já salva, ou "sem imagem").
 *
 * Convenção de marcação esperada, por campo de upload:
 *   <div data-media-group>
 *     <img data-media-preview="image" ...>          (opcional)
 *     <video data-media-preview="video" ...></video> (opcional, para vídeo)
 *     <div data-media-placeholder>...</div>          (opcional)
 *     <span data-media-filename></span>              (opcional)
 *     <button type="button" data-media-clear>...</button>
 *     <input type="file" ...>
 *   </div>
 */
(function () {
  function revokeIfBlob(url) {
    if (url && url.indexOf('blob:') === 0) {
      try {
        URL.revokeObjectURL(url);
      } catch (e) {
        /* ignora */
      }
    }
  }

  function setup(group) {
    var input = group.querySelector('input[type="file"]');
    if (!input) return;

    var previewImg = group.querySelector('[data-media-preview="image"]');
    var previewVideo = group.querySelector('[data-media-preview="video"]');
    var placeholder = group.querySelector('[data-media-placeholder]');
    var clearBtn = group.querySelector('[data-media-clear]');
    var nameBadge = group.querySelector('[data-media-filename]');

    // Guarda o estado original (imagem/vídeo já salvo) para poder restaurar
    // quando o usuário cancelar a seleção de um novo arquivo.
    if (previewImg && previewImg.getAttribute('src')) {
      previewImg.dataset.originalSrc = previewImg.getAttribute('src');
    }
    if (previewVideo && previewVideo.getAttribute('src')) {
      previewVideo.dataset.originalSrc = previewVideo.getAttribute('src');
    }
    var hadOriginalImage = !!(previewImg && previewImg.dataset.originalSrc);
    var hadOriginalVideo = !!(previewVideo && previewVideo.dataset.originalSrc);
    var hadOriginalMedia = hadOriginalImage || hadOriginalVideo;

    function showImagePreview(file) {
      if (!previewImg) return;
      revokeIfBlob(previewImg.dataset.blobUrl);
      var url = URL.createObjectURL(file);
      previewImg.dataset.blobUrl = url;
      previewImg.src = url;
      previewImg.classList.remove('hidden');
      if (previewVideo) previewVideo.classList.add('hidden');
    }

    function showVideoPreview(file) {
      if (!previewVideo) return;
      revokeIfBlob(previewVideo.dataset.blobUrl);
      var url = URL.createObjectURL(file);
      previewVideo.dataset.blobUrl = url;
      previewVideo.src = url;
      previewVideo.load();
      previewVideo.classList.remove('hidden');
      if (previewImg) previewImg.classList.add('hidden');
    }

    function resetPreview() {
      input.value = '';

      if (previewVideo) {
        revokeIfBlob(previewVideo.dataset.blobUrl);
        if (hadOriginalVideo) {
          previewVideo.src = previewVideo.dataset.originalSrc;
          previewVideo.load();
          previewVideo.classList.remove('hidden');
        } else {
          previewVideo.removeAttribute('src');
          previewVideo.classList.add('hidden');
        }
      }

      if (previewImg) {
        revokeIfBlob(previewImg.dataset.blobUrl);
        if (hadOriginalImage) {
          previewImg.src = previewImg.dataset.originalSrc;
          previewImg.classList.remove('hidden');
        } else {
          previewImg.removeAttribute('src');
          previewImg.classList.add('hidden');
        }
      }

      if (placeholder) {
        placeholder.classList.toggle('hidden', hadOriginalMedia);
      }
      if (nameBadge) {
        nameBadge.textContent = '';
        nameBadge.classList.add('hidden');
      }
      if (clearBtn) clearBtn.classList.add('hidden');
    }

    input.addEventListener('change', function () {
      var file = input.files && input.files[0];
      if (!file) {
        resetPreview();
        return;
      }

      if (file.type.indexOf('video/') === 0) {
        showVideoPreview(file);
      } else {
        showImagePreview(file);
      }

      if (placeholder) placeholder.classList.add('hidden');
      if (nameBadge) {
        nameBadge.textContent = file.name;
        nameBadge.classList.remove('hidden');
      }
      if (clearBtn) clearBtn.classList.remove('hidden');
    });

    if (clearBtn) {
      clearBtn.addEventListener('click', function () {
        resetPreview();
      });
    }
  }

  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('[data-media-group]').forEach(setup);
  });
})();
