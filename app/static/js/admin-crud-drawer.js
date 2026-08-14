// Gaveta lateral genérica de criar/editar usada nas telas de conteúdo do
// admin (Vantagens, Galeria, Depoimentos, Parceiros, Seções Personalizadas
// e seus cartões): abre/fecha sem depender de navegação sempre que
// possível. O formulário já vem renderizado pelo servidor (com os dados do
// item em edição, se houver) -- este script só controla a exibição.
// Carregado globalmente (base_admin.html); não faz nada em páginas sem
// [data-crud-drawer].
document.addEventListener('DOMContentLoaded', () => {
  const drawer = document.querySelector('[data-crud-drawer]');
  const backdrop = document.querySelector('[data-crud-drawer-backdrop]');
  const addBtn = document.querySelector('[data-crud-drawer-add]');
  const closeBtn = document.querySelector('[data-crud-drawer-close]');
  if (!drawer || !backdrop || !addBtn || !closeBtn) return;

  const isEditing = drawer.dataset.editing === 'true';

  function openDrawer() {
    drawer.classList.add('open');
    backdrop.classList.add('open');
    drawer.setAttribute('aria-hidden', 'false');
    const firstField = drawer.querySelector('.side-drawer-body input, .side-drawer-body textarea');
    if (firstField) firstField.focus({ preventScroll: true });
  }

  function closeDrawer() {
    drawer.classList.remove('open');
    backdrop.classList.remove('open');
    drawer.setAttribute('aria-hidden', 'true');
  }

  // Editando um item existente (veio de um link "Editar#form-card") ou
  // acabou de chegar aqui pelo botão "+ Novo" (mesma âncora): abre já na
  // primeira renderização, sem esperar clique.
  if (isEditing || window.location.hash === '#form-card') {
    openDrawer();
  }

  addBtn.addEventListener('click', (event) => {
    // Sem item em edição, o formulário em branco já está pronto no DOM --
    // só mostra a gaveta, sem recarregar a página.
    if (!isEditing) {
      event.preventDefault();
      openDrawer();
    }
    // Editando: deixa o link navegar de verdade para a rota de criação,
    // já que o <form> desta página está apontado para atualizar o item atual.
  });

  closeBtn.addEventListener('click', (event) => {
    if (!isEditing) {
      event.preventDefault();
      closeDrawer();
    }
    // Editando: deixa o link navegar para limpar o estado de edição.
  });

  backdrop.addEventListener('click', closeDrawer);

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && drawer.classList.contains('open')) closeDrawer();
  });
});
