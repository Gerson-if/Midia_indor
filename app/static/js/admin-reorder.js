/**
 * Reordenação de cards por arrastar e soltar (drag and drop), nas telas de
 * conteúdo do painel admin (Vantagens, Galeria, Depoimentos, Parceiros).
 *
 * Antes, a única forma de mudar a posição de um item era abrir a edição e
 * digitar manualmente um número em "Ordem" — fácil de errar (dois itens
 * com o mesmo número, por exemplo) e nada intuitivo. Aqui, cada card vira
 * arrastável (native HTML5 Drag and Drop, sem dependências externas) e,
 * ao soltar, a nova ordem completa é enviada para o servidor via fetch.
 *
 * Marcação esperada:
 *   <div data-reorder-list data-reorder-url="{{ url_for(...) }}">
 *     <div data-reorder-item data-id="{{ item.id }}"> ... </div>
 *     ...
 *   </div>
 */
(function () {
  function csrfToken() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.content : '';
  }

  function getItems(list) {
    return Array.prototype.slice.call(list.querySelectorAll(':scope > [data-reorder-item]'));
  }

  function currentOrder(list) {
    return getItems(list).map(function (el) {
      return el.dataset.id;
    });
  }

  function setup(list) {
    var url = list.dataset.reorderUrl;
    if (!url) return;

    var draggedEl = null;
    var originalOrder = null;
    var saving = false;

    getItems(list).forEach(function (item) {
      var handle = item.querySelector('[data-drag-handle]') || item;
      item.setAttribute('draggable', 'true');

      // Só inicia o arraste a partir da "alça" (ícone de grip), para não
      // atrapalhar cliques/seleção de texto no resto do card — mas o
      // elemento arrastável continua sendo o card inteiro.
      handle.addEventListener('mousedown', function () {
        item.dataset.dragReady = '1';
      });
      item.addEventListener('dragstart', function (evt) {
        if (handle !== item && item.dataset.dragReady !== '1') {
          evt.preventDefault();
          return;
        }
        item.dataset.dragReady = '';
        draggedEl = item;
        originalOrder = currentOrder(list);
        item.classList.add('is-dragging');
        evt.dataTransfer.effectAllowed = 'move';
        try {
          evt.dataTransfer.setData('text/plain', item.dataset.id);
        } catch (e) {
          /* alguns navegadores exigem setData mesmo sem uso real */
        }
      });

      item.addEventListener('dragend', function () {
        item.classList.remove('is-dragging');
        clearDragOverStyles();
        if (draggedEl === item) {
          persistOrder(list, originalOrder);
        }
        draggedEl = null;
      });

      item.addEventListener('dragover', function (evt) {
        if (!draggedEl || draggedEl === item) return;
        evt.preventDefault();
        evt.dataTransfer.dropEffect = 'move';

        var rect = item.getBoundingClientRect();
        var isVertical = rect.height > rect.width * 0.6;
        var before;
        if (isVertical) {
          before = evt.clientY - rect.top < rect.height / 2;
        } else {
          before = evt.clientX - rect.left < rect.width / 2;
        }

        clearDragOverStyles();
        item.classList.add(before ? 'drag-over-top' : 'drag-over-bottom');

        if (before) {
          list.insertBefore(draggedEl, item);
        } else {
          list.insertBefore(draggedEl, item.nextSibling);
        }
      });
    });

    function clearDragOverStyles() {
      getItems(list).forEach(function (el) {
        el.classList.remove('drag-over-top', 'drag-over-bottom');
      });
    }

    function persistOrder(list, previousOrder) {
      var newOrder = currentOrder(list);
      var changed =
        newOrder.length !== previousOrder.length ||
        newOrder.some(function (id, idx) {
          return id !== previousOrder[idx];
        });
      if (!changed || saving) return;

      saving = true;
      fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrfToken(),
        },
        body: JSON.stringify({ order: newOrder.map(Number) }),
      })
        .then(function (resp) {
          return resp.json().then(function (data) {
            return { ok: resp.ok, data: data };
          });
        })
        .then(function (result) {
          saving = false;
          if (result.ok && result.data && result.data.success) {
            if (window.showToast) window.showToast('Ordem atualizada.', 'success');
          } else {
            throw new Error((result.data && result.data.message) || 'Falha ao salvar a nova ordem.');
          }
        })
        .catch(function (err) {
          saving = false;
          if (window.showToast) {
            window.showToast(err.message || 'Não foi possível salvar a nova ordem. Recarregando...', 'danger');
          }
          // Estado local pode ter divergido do servidor — recarrega para
          // garantir consistência em vez de deixar a tela "mentindo".
          setTimeout(function () {
            window.location.reload();
          }, 1200);
        });
    }
  }

  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('[data-reorder-list]').forEach(setup);
  });
})();
