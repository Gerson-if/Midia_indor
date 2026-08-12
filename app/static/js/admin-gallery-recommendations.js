// Lista dinâmica de "Recomendado para" no formulário de galeria (admin):
// adiciona/remove linhas (ícone + texto) sem recarregar a página, clonando
// o <template> com os mesmos widgets que o WTForms usaria para a próxima
// posição da lista (nome/id com "__INDEX__" trocado pelo próximo índice).
document.addEventListener('DOMContentLoaded', () => {
  const list = document.getElementById('recommendations-list');
  const addBtn = document.getElementById('add-recommendation');
  const template = document.getElementById('recommendation-row-template');
  if (!list || !addBtn || !template) return;

  let nextIndex = parseInt(list.dataset.nextIndex || '0', 10);

  function addRow() {
    const clone = template.content.cloneNode(true);
    clone.querySelectorAll('[name], [id]').forEach((el) => {
      if (el.name) el.name = el.name.replace('__INDEX__', String(nextIndex));
      if (el.id) el.id = el.id.replace('__INDEX__', String(nextIndex));
    });
    list.appendChild(clone);
    nextIndex += 1;
  }

  addBtn.addEventListener('click', addRow);

  list.addEventListener('click', (event) => {
    const removeBtn = event.target.closest('[data-remove-recommendation]');
    if (!removeBtn) return;
    removeBtn.closest('.recommendation-row').remove();
  });

  // Começa com uma linha em branco pronta pra preencher, em vez de uma
  // lista vazia só com o botão "+".
  if (list.children.length === 0) addRow();
});
