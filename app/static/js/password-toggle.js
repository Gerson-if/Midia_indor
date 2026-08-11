document.addEventListener("DOMContentLoaded", function () {
  document.querySelectorAll("[data-password-toggle]").forEach(function (btn) {
    var wrapper = btn.closest("[data-password-field]");
    var input = wrapper && wrapper.querySelector("input");
    var showIcon = btn.querySelector("[data-icon-show]");
    var hideIcon = btn.querySelector("[data-icon-hide]");
    if (!input || !showIcon || !hideIcon) return;

    btn.addEventListener("click", function () {
      var willShow = input.type === "password";
      input.type = willShow ? "text" : "password";
      showIcon.classList.toggle("hidden", willShow);
      hideIcon.classList.toggle("hidden", !willShow);
      btn.setAttribute("aria-label", willShow ? "Ocultar senha" : "Mostrar senha");
    });
  });
});
