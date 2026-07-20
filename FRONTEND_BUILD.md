# Front-end estático (Tailwind CSS + fontes) — como rebuildar

O projeto usa **Tailwind CSS compilado estaticamente** (sem CDN em runtime) e
**fontes self-hosted** (sem Google Fonts). Os arquivos finais já ficam
prontos em `app/static/css/tailwind.min.css` e `app/static/fonts/`, então
**não é obrigatório** rodar nada para o site funcionar — só é necessário
reinstalar/recompilar se você **alterar classes Tailwind nos templates**.

## Instalação (uma vez)

```bash
npm install
```

## Rebuildar o CSS depois de editar templates

```bash
npm run build:css        # gera app/static/css/tailwind.min.css (minificado)
# ou, durante o desenvolvimento, para recompilar automaticamente a cada mudança:
npm run watch:css
```

O Tailwind é configurado em `tailwind.config.js` — ele escaneia
`app/templates/**/*.html` e `app/static/js/**/*.js` em busca de classes
usadas e gera apenas o CSS necessário (build "JIT" purgado).

## Fontes

As fontes (Space Grotesk, IBM Plex Sans, JetBrains Mono) foram baixadas via
pacotes `@fontsource/*` do npm e os arquivos `.woff2` necessários já estão
copiados em `app/static/fonts/`, referenciados por `app/static/css/fonts.css`.
Não há chamada externa a `fonts.googleapis.com`/`fonts.gstatic.com` — tudo é
servido localmente pelo próprio Flask, o que reduz round-trips de DNS/TLS e
elimina uma dependência externa.

Caso queira adicionar um novo peso/fonte, adicione o pacote `@fontsource`
correspondente, copie o(s) `.woff2` para `app/static/fonts/` e declare o
`@font-face` em `app/static/css/fonts.css`.

## Estrutura

- `assets/input.css` — ponto de entrada do Tailwind (`@tailwind base/components/utilities`)
- `tailwind.config.js` — mapeia as cores customizadas do tema (ink, panel, amber, cyan, hi/mid/low...) para as CSS vars já definidas em `app/static/css/style.css`
- `app/static/css/tailwind.min.css` — build final, servido pelo Flask
- `app/static/css/fonts.css` — `@font-face` locais
- `app/static/fonts/` — arquivos `.woff2`
