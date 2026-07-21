/**
 * Modal de confirmação compacto para ações de exclusão no painel admin,
 * substituindo o `confirm()` nativo do navegador (feio, não estilizável
 * e sem identidade visual com o resto do painel).
 *
 * Convenção: qualquer <form> com o atributo `data-confirm-message="..."`
 * passa a exibir este modal antes de enviar. Basta remover o antigo
 * `onsubmit="return confirm(...)"` e adicionar o atributo no lugar.
 */
(function () {
  var overlay = null;
  var pendingForm = null;

  function build() {
    var el = document.createElement('div');
    el.className = 'confirm-modal-overlay hidden';
    el.innerHTML =
      '<div class="confirm-modal" role="alertdialog" aria-modal="true">' +
      '<p class="confirm-modal-message"></p>' +
      '<div class="confirm-modal-actions">' +
      '<button type="button" class="confirm-modal-cancel">Cancelar</button>' +
      '<button type="button" class="confirm-modal-confirm">Excluir</button>' +
      '</div>' +
      '</div>';
    document.body.appendChild(el);
    return el;
  }

  function open(form) {
    pendingForm = form;
    overlay.querySelector('.confirm-modal-message').textContent =
      form.dataset.confirmMessage || 'Confirma esta ação?';
    overlay.classList.remove('hidden');
  }

  function close() {
    overlay.classList.add('hidden');
    pendingForm = null;
  }

  document.addEventListener('DOMContentLoaded', function () {
    var forms = document.querySelectorAll('form[data-confirm-message]');
    if (!forms.length) return;

    overlay = build();

    overlay.addEventListener('click', function (evt) {
      if (evt.target === overlay) close();
    });
    document.addEventListener('keydown', function (evt) {
      if (evt.key === 'Escape' && !overlay.classList.contains('hidden')) close();
    });
    overlay.querySelector('.confirm-modal-cancel').addEventListener('click', close);
    overlay.querySelector('.confirm-modal-confirm').addEventListener('click', function () {
      var form = pendingForm;
      close();
      // form.submit() não dispara o evento "submit" novamente, então não
      // há risco de reabrir o modal em loop.
      if (form) form.submit();
    });

    forms.forEach(function (form) {
      form.addEventListener('submit', function (evt) {
        evt.preventDefault();
        open(form);
      });
    });
  });
})();
