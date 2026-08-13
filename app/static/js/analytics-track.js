// Envia quanto tempo o visitante ficou na página (dashboard do admin:
// "tempo médio na página"). Só existe window.__NX_PV_ID__ quando o backend
// registrou uma visualização rastreável (ver app/services/analytics.py) --
// sem isso, este script não faz nada.
(function () {
  var pageViewId = window.__NX_PV_ID__;
  var startedAt = window.__NX_PV_START__;
  if (!pageViewId || !startedAt) return;

  var sent = false;

  function sendDuration() {
    if (sent) return;
    var elapsedSeconds = Math.round((Date.now() - startedAt) / 1000);
    if (elapsedSeconds < 1) return;
    sent = true;

    var url = '/api/v1/track/duracao';
    var payload = JSON.stringify({ page_view_id: pageViewId, duration: elapsedSeconds });

    if (navigator.sendBeacon) {
      navigator.sendBeacon(url, new Blob([payload], { type: 'application/json' }));
    } else {
      fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: payload, keepalive: true });
    }
  }

  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'hidden') sendDuration();
  });
  window.addEventListener('pagehide', sendDuration);
})();
