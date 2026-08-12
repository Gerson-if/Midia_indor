// Nos cards da galeria que têm página de detalhes (data-detail-link), em
// telas sem mouse de verdade o primeiro toque só "arma" o card (mostra a
// animação/selo confirmando a intenção) em vez de navegar direto -- só o
// segundo toque, ou um clique com mouse/teclado, segue o link. Evita o
// "cliquei sem querer e já saí da galeria" no celular, já que lá não existe
// hover para avisar antes que o card é clicável.
// Em dispositivos com mouse (hover:hover e pointer:fine), o hover já avisa
// visualmente antes do clique -- por isso o script nem entra em ação lá,
// e o primeiro clique já navega normalmente.
(function () {
  if (window.matchMedia && window.matchMedia('(hover: hover) and (pointer: fine)').matches) {
    return;
  }

  var ARMED_CLASS = 'is-armed';
  var DISARM_DELAY_MS = 2600;
  var armedLink = null;
  var armedTimer = null;

  function disarm(link) {
    if (!link) return;
    link.classList.remove(ARMED_CLASS);
    if (armedTimer) {
      clearTimeout(armedTimer);
      armedTimer = null;
    }
    if (armedLink === link) armedLink = null;
  }

  document.querySelectorAll('[data-detail-link]').forEach(function (link) {
    link.addEventListener('click', function (event) {
      if (link.classList.contains(ARMED_CLASS)) {
        return; // segundo toque: deixa navegar normalmente
      }
      event.preventDefault();
      if (armedLink && armedLink !== link) disarm(armedLink);
      link.classList.add(ARMED_CLASS);
      armedLink = link;
      armedTimer = setTimeout(function () {
        disarm(link);
      }, DISARM_DELAY_MS);
    });
  });

  // Tocar fora de um card armado desarma ele, em vez de deixar o selo
  // "toque de novo" aceso indefinidamente até o timeout.
  document.addEventListener(
    'touchstart',
    function (event) {
      if (armedLink && !armedLink.contains(event.target)) disarm(armedLink);
    },
    { passive: true }
  );
})();
