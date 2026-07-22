/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/templates/**/*.html",
    "./app/static/js/**/*.js",
  ],
  // O tema (claro/escuro) é definido em runtime via `<html data-theme="...">`
  // (ver app/static/css/style.css), lido de SiteSettings.theme e escolhido
  // pelo admin em Configurações → Aparência — não usamos o "darkMode" do
  // Tailwind porque não é uma preferência de SO/navegador por visitante,
  // e sim uma configuração única para o sistema inteiro.
  theme: {
    extend: {
      colors: {
        ink: "var(--ink)",
        inksoft: "var(--ink-soft)",
        panel: "var(--panel)",
        panel2: "var(--panel-2)",
        line: "var(--line)",
        amber: "var(--amber)",
        "amber-dim": "var(--amber-dim)",
        cyan: "var(--cyan)",
        paper: "var(--paper)",
        hi: "var(--text-hi)",
        mid: "var(--text-mid)",
        low: "var(--text-low)",
        onbrand: "var(--on-brand)",
      },
      fontFamily: {
        display: ["Space Grotesk", "system-ui", "sans-serif"],
        body: ["IBM Plex Sans", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
      },
      maxWidth: {
        nx: "1240px",
      },
      transitionProperty: {
        width: "width, margin",
      },
    },
  },
  // Utilitários usados apenas dentro de <style> blocks server-side (não
  // literais em templates) ou montados via JS ficam protegidos aqui para
  // não serem removidos pelo processo de purge do Tailwind.
  safelist: [
    "hidden",
    "block",
    "flex",
    "rotate-180",
    { pattern: /^(bg|text|border)-(red|green|amber|cyan)-(300|400|500)$/ },
  ],
  plugins: [],
};
