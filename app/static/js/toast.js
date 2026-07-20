/**
 * Sistema de notificações toast — leve, sem dependências.
 * Lê as mensagens flash renderizadas pelo servidor (elementos com a
 * classe .flash-data, escondidos) e as exibe como toasts discretos,
 * com auto-dismiss e botão de fechar manual.
 *
 * Também expõe window.showToast(message, type) para uso via JS
 * (ex.: feedback de ações via fetch/AJAX no futuro).
 */
(function () {
  const TYPE_STYLES = {
    success: { border: '#22C55E', icon: '✓' },
    danger: { border: '#EF4444', icon: '✕' },
    warning: { border: '#FFB020', icon: '!' },
    info: { border: '#37D6C7', icon: 'i' },
  };

  function ensureContainer() {
    let container = document.getElementById('toast-container');
    if (!container) {
      container = document.createElement('div');
      container.id = 'toast-container';
      container.setAttribute('aria-live', 'polite');
      container.style.cssText = [
        'position:fixed', 'top:1rem', 'right:1rem', 'z-index:9999',
        'display:flex', 'flex-direction:column', 'gap:.6rem',
        'max-width:22rem', 'width:calc(100% - 2rem)',
      ].join(';');
      document.body.appendChild(container);
    }
    return container;
  }

  function showToast(message, type) {
    type = TYPE_STYLES[type] ? type : 'info';
    const style = TYPE_STYLES[type];
    const container = ensureContainer();

    const toast = document.createElement('div');
    toast.setAttribute('role', 'status');
    toast.style.cssText = [
      'display:flex', 'align-items:flex-start', 'gap:.6rem',
      'background:#131A24', 'color:#ECEEF2',
      'border-left:4px solid ' + style.border,
      'border-radius:10px', 'padding:.75rem .9rem',
      'box-shadow:0 8px 24px rgba(0,0,0,.35)',
      'font-size:.825rem', 'line-height:1.4',
      'opacity:0', 'transform:translateX(12px)',
      'transition:opacity .25s ease, transform .25s ease',
    ].join(';');

    const iconEl = document.createElement('span');
    iconEl.textContent = style.icon;
    iconEl.style.cssText = [
      'flex-shrink:0', 'width:1.25rem', 'height:1.25rem', 'border-radius:999px',
      'display:flex', 'align-items:center', 'justify-content:center',
      'font-size:.7rem', 'font-weight:700', 'color:#0A0E16',
      'background:' + style.border,
    ].join(';');

    const textEl = document.createElement('span');
    textEl.textContent = message;
    textEl.style.cssText = 'flex:1;';

    const closeEl = document.createElement('button');
    closeEl.setAttribute('aria-label', 'Fechar notificação');
    closeEl.textContent = '×';
    closeEl.style.cssText = [
      'flex-shrink:0', 'background:transparent', 'border:none', 'cursor:pointer',
      'color:#6C7686', 'font-size:1rem', 'line-height:1', 'padding:0',
    ].join(';');

    toast.appendChild(iconEl);
    toast.appendChild(textEl);
    toast.appendChild(closeEl);
    container.appendChild(toast);

    requestAnimationFrame(() => {
      toast.style.opacity = '1';
      toast.style.transform = 'translateX(0)';
    });

    let dismissed = false;
    const dismiss = () => {
      if (dismissed) return;
      dismissed = true;
      toast.style.opacity = '0';
      toast.style.transform = 'translateX(12px)';
      setTimeout(() => toast.remove(), 250);
    };

    closeEl.addEventListener('click', dismiss);
    const timer = setTimeout(dismiss, type === 'danger' ? 7000 : 4500);
    toast.addEventListener('mouseenter', () => clearTimeout(timer));
  }

  function normalizeCategory(category) {
    if (category === 'error') return 'danger';
    if (['success', 'danger', 'warning', 'info'].includes(category)) return category;
    return 'info';
  }

  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.flash-data').forEach((el) => {
      const category = normalizeCategory(el.dataset.category || 'info');
      const message = el.textContent.trim();
      if (message) showToast(message, category);
      el.remove();
    });
  });

  window.showToast = showToast;
})();
