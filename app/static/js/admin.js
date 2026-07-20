/**
 * Comportamento da sidebar do painel admin:
 * - Recolher/expandir (desktop), com estado salvo em localStorage.
 * - Abrir/fechar como gaveta (drawer) no mobile, com backdrop.
 */
(function () {
  var STORAGE_KEY = "admin_sidebar_collapsed";
  var html = document.documentElement;

  function setCollapsed(collapsed) {
    html.classList.toggle("sidebar-collapsed", collapsed);
    try {
      localStorage.setItem(STORAGE_KEY, collapsed ? "1" : "0");
    } catch (e) {
      /* localStorage indisponível (modo privado, etc.) — ignora silenciosamente */
    }
  }

  function openMobileMenu() {
    html.classList.add("mobile-sidebar-open");
  }

  function closeMobileMenu() {
    html.classList.remove("mobile-sidebar-open");
  }

  document.addEventListener("DOMContentLoaded", function () {
    var toggleBtn = document.getElementById("sidebar-toggle");
    var mobileBtn = document.getElementById("mobile-menu-btn");
    var backdrop = document.getElementById("sidebar-backdrop");

    if (toggleBtn) {
      toggleBtn.addEventListener("click", function () {
        setCollapsed(!html.classList.contains("sidebar-collapsed"));
      });
    }

    if (mobileBtn) {
      mobileBtn.addEventListener("click", openMobileMenu);
    }
    if (backdrop) {
      backdrop.addEventListener("click", closeMobileMenu);
    }

    // Fecha a gaveta mobile automaticamente ao navegar para outra página.
    document.querySelectorAll(".sidebar .nav-item").forEach(function (link) {
      link.addEventListener("click", closeMobileMenu);
    });

    // Fecha a gaveta mobile com a tecla Esc.
    document.addEventListener("keydown", function (evt) {
      if (evt.key === "Escape") closeMobileMenu();
    });
  });
})();
