# Nexo Mídia — Backend

Backend completo em Flask para o site institucional e painel administrativo
de mídia indoor digital. PostgreSQL em produção, SQLite em desenvolvimento/testes.

## Sumário

- [Arquitetura](#arquitetura)
- [Requisitos](#requisitos)
- [Desenvolvimento local](#desenvolvimento-local)
- [Testes](#testes)
- [Migrations](#migrations)
- [Variáveis de ambiente](#variáveis-de-ambiente)
- [Deploy em VPS Ubuntu (guiado, sem Docker)](#deploy-em-vps-ubuntu)
- [Segurança implementada](#segurança-implementada)
- [API](#api)

## Arquitetura

```
app/
├── blueprints/         # main (site), auth, admin, api/v1
├── models/              # User, Proposal, conteúdo do site, AuditLog
├── services/             # geração de link WhatsApp, upload seguro
├── utils/                # decorators (RBAC), erros padronizados, logging
├── templates/            # Jinja2 (site público + painel admin)
├── static/                # CSS, imagens, uploads
├── config.py              # Development / Testing / Production
└── extensions.py          # instâncias únicas das libs (db, login, csrf...)
deploy/                    # Scripts de instalação/atualização, Nginx, Gunicorn, systemd
migrations/                 # Flask-Migrate / Alembic
scripts/seed.py              # dados de demonstração
tests/                        # pytest
```

Principais decisões:

- **App Factory + Blueprints**: `create_app()` monta a aplicação, facilitando
  testes isolados e múltiplos ambientes.
- **SQLAlchemy + Flask-Migrate**: schema versionado, nunca `db.create_all()`
  em produção.
- **Controle de concorrência otimista** (`version_id_col`) em `Proposal`,
  `User` e `SiteSettings`, evitando que duas edições simultâneas se
  sobrescrevam silenciosamente.
- **Auditoria** (`AuditLog`): toda ação sensível (login, mudança de status,
  contato via WhatsApp, exclusões) é registrada, com IP e usuário.

## Requisitos

- Python 3.11+
- PostgreSQL 14+ (produção) — SQLite já vem pronto para dev/testes
- (Opcional) Redis, para rate limiting distribuído em produção com múltiplos workers

## Desenvolvimento local

```bash
# 1. Clonar/entrar no projeto e criar o ambiente virtual
python3 -m venv venv
source venv/bin/activate

# 2. Instalar dependências (requirements.txt já inclui as de testes/qualidade
#    de código — pytest, flake8, black, isort etc. — não há um arquivo separado)
pip install -r requirements.txt

# 3. Configurar variáveis de ambiente
cp .env.example .env
# edite o .env: gere uma SECRET_KEY forte, defina ADMIN_EMAIL/ADMIN_PASSWORD etc.
python -c "import secrets; print(secrets.token_hex(32))"   # gera uma chave forte

# 4. Criar as pastas locais necessárias
mkdir -p instance logs

# 5. Aplicar as migrations (cria o schema no SQLite de desenvolvimento)
export FLASK_APP=wsgi.py FLASK_ENV=development   # (no Windows: set em vez de export)
flask db upgrade

# 6. Criar o usuário administrador inicial
flask create-admin

# 7. (Opcional) popular com conteúdo de demonstração
flask seed-demo

# 8. Rodar o servidor de desenvolvimento
flask run
# ou: python wsgi.py
```

Acesse `http://localhost:5000` para o site público e
`http://localhost:5000/login` para o painel administrativo.

> **Acessando de outra máquina/ambiente (VM, container, servidor de teste)?**
> `flask run` escuta por padrão apenas em `127.0.0.1` (só aceita conexões da
> própria máquina). O `.env.example` já define `FLASK_RUN_HOST=0.0.0.0` para
> que o Flask CLI escute em todas as interfaces — copie o `.env` normalmente
> e o `flask run` já vai funcionar acessando pelo IP/domínio do ambiente
> remoto. Sem essa variável (ou passando `--host 127.0.0.1` manualmente), a
> conexão externa é recusada e parece que a aplicação "só entende localhost".

## Testes

```bash
pytest                      # roda toda a suíte
pytest --cov=app tests/      # com cobertura
```

Os testes usam `TestingConfig` (SQLite em memória, CSRF desabilitado,
rate limiting desabilitado) — nunca tocam o banco de desenvolvimento/produção.

## Migrations

```bash
# Depois de alterar um model:
flask db migrate -m "descrição da mudança"
# revise o arquivo gerado em migrations/versions/ antes de aplicar!
flask db upgrade

# Reverter a última migration:
flask db downgrade
```

## Variáveis de ambiente

Veja `.env.example` para a lista completa e comentada. As mais importantes:

| Variável | Descrição |
|---|---|
| `FLASK_ENV` | `development`, `testing` ou `production` |
| `SECRET_KEY` | Chave de sessão/CSRF — **obrigatória e única em produção** |
| `DATABASE_URL` | `postgresql+psycopg2://usuario:senha@host:5432/banco` em produção |
| `COMPANY_WHATSAPP` | Número da empresa (com DDI), usado no botão flutuante do site |
| `RATELIMIT_STORAGE_URI` | `memory://` em dev; `redis://host:6379/0` em produção com múltiplos workers |
| `UPLOAD_FOLDER` / `MAX_CONTENT_LENGTH_MB` | Configuração de upload de imagens/vídeos |
| `BEHIND_PROXY` | `1` quando atrás de Nginx (ativa `ProxyFix`) |
| `FORCE_HTTPS` | `1` em produção (Talisman força HTTPS e HSTS) |

Em produção, `ProductionConfig.validate()` interrompe a inicialização se
`SECRET_KEY` estiver com o valor de desenvolvimento — evita subir com
segredo inseguro por engano.

## Deploy em VPS Ubuntu

Deploy nativo (sem Docker) com um instalador guiado: Nginx + Gunicorn +
systemd, com PostgreSQL ou SQLite à sua escolha, HTTPS automático via
Let's Encrypt (se você tiver domínio) ou acesso direto por IP. Layout
de **pasta única** (sem releases/symlinks): o app inteiro fica em
`/opt/midia-indoor`, e atualizar é essencialmente um `git pull`.

Veja o guia completo em **[`deploy/README.md`](deploy/README.md)**.

Resumo rápido — na VPS (Ubuntu 22.04/24.04), de preferência clonando
via Git (facilita as atualizações depois):

```bash
git clone <url-do-seu-repositorio> midia-indoor && cd midia-indoor
sudo bash deploy/scripts/install.sh
```

O script pergunta tudo que precisa (domínio ou IP, banco de dados,
Redis, HTTPS, dados da empresa e do administrador) e deixa o site no ar.

Para publicar atualizações depois:

```bash
cd /opt/midia-indoor
sudo bash deploy/scripts/update.sh
```

Isso faz backup do banco, aplica o `git pull`, roda as migrações,
reinicia o serviço e confere `/healthz` — revertendo automaticamente
(`git reset --hard`) se a nova versão não responder. Detalhes de cada
script em [`deploy/README.md`](deploy/README.md).

## Segurança implementada

- **CSRF**: todos os formulários usam Flask-WTF (`hidden_tag()` injeta o token).
- **XSS**: autoescape do Jinja2 ativo por padrão + CSP via Flask-Talisman.
- **SQL Injection**: 100% via ORM SQLAlchemy (nenhuma query SQL bruta com
  interpolação de string).
- **Sessões**: cookies `HttpOnly`, `SameSite=Lax`, `Secure` em produção,
  expiração configurável, proteção "strong" do Flask-Login (invalida sessão
  se IP/User-Agent mudarem de forma suspeita).
- **Senhas**: hashing com bcrypt (Flask-Bcrypt).
- **Rate limiting**: Flask-Limiter no login (10/min) e no formulário público
  de propostas (5/min, 20/hora), evitando força bruta e spam.
- **Bloqueio de conta**: 5 tentativas de login inválidas bloqueiam a conta
  por 15 minutos.
- **Upload seguro**: whitelist de extensão + validação de MIME real via
  `python-magic` + reprocessamento de imagens com Pillow (remove EXIF/metadados
  maliciosos) + nomes de arquivo gerados via UUID.
- **Autorização por papel (RBAC)**: `admin`, `editor`, `viewer`, aplicado via
  decorators em todas as rotas sensíveis.
- **Auditoria**: tabela `audit_logs` append-only com IP, usuário e ação.
- **Concorrência**: controle otimista (`version_id`) evita que edições
  simultâneas se percam silenciosamente.
- **Cabeçalhos de segurança**: CSP, HSTS, `X-Frame-Options`,
  `X-Content-Type-Options`, `Referrer-Policy` via Flask-Talisman + Nginx.
- **Erros padronizados**: JSON consistente em `/api/*`, páginas HTML
  amigáveis nas demais rotas; nenhum stack trace exposto em produção.

## Performance

- **CSS compilado estaticamente**: nada de compilar Tailwind em tempo real
  no navegador (o CDN oficial do Tailwind não é recomendado para produção
  por isso). O CSS final (`app/static/css/tailwind.min.css`) já vem
  pronto e minificado.
- **Bibliotecas hospedadas localmente**: AOS e Chart.js não dependem de
  CDNs externos (`unpkg`, `jsdelivr`), eliminando requisições externas e
  pontos de falha.
- **Compressão automática**: Flask-Compress comprime as respostas (gzip).
- **Imagens otimizadas automaticamente no upload**: toda imagem enviada é
  redimensionada conforme o contexto de uso (logo de parceiro não precisa
  da mesma resolução de uma foto de galeria) e convertida para WEBP.
- **Workers do Gunicorn com padrão conservador**: evita sobrecarregar
  VPS pequenas por padrão (ajustável via `GUNICORN_WORKERS`).

## Painel administrativo

Todas as seções de conteúdo (Vantagens, Galeria, Depoimentos, Parceiros)
possuem CRUD completo: **Criar, Listar, Editar e Excluir**. Clique em
"Editar" em qualquer item da lista para carregar o formulário já
preenchido.

A tela de Configurações do site (`/admin/configuracoes`) tem um painel de
**pré-visualização ao vivo** do Hero (título, subtítulo, cores, vídeo) que
atualiza conforme você digita, sem precisar salvar.

O Dashboard exibe gráficos reais (Chart.js) de solicitações recebidas nos
últimos 14 dias e de distribuição por status.

### Mídia do Hero (vídeo ou imagem)

Em Configurações → Mídia de Capa do Hero, o administrador escolhe se o
topo do site exibe um **vídeo** ou uma **imagem estática**, com upload,
substituição e remoção diretamente pelo painel — sem tocar em código.
Vídeos enviados são automaticamente otimizados via `ffmpeg`: redimensionados
para no máximo 1920×1080, recodificados em H.264 e com o áudio removido
(o vídeo do Hero é sempre exibido mudo), reduzindo drasticamente o
tamanho do arquivo. A pré-visualização ao vivo reflete a alternância
entre vídeo e imagem em tempo real, antes mesmo de salvar.

### Páginas legais editáveis

O conteúdo de `/privacidade` e `/termos` é armazenado no banco e editado
em Configurações → Páginas Legais. Use linhas iniciadas com `## ` para
criar títulos de seção; parágrafos são separados por uma linha em branco.

### Notificações (toasts)

Mensagens de sucesso, erro e aviso são exibidas como notificações
discretas no canto superior direito (auto-dismiss, com botão de fechar),
tanto no site público quanto no painel administrativo.

## API

Endpoints REST em `/api/v1`, prontos para futuras integrações (CRM, app
mobile, totens):

- `POST /api/v1/proposals` — cria uma solicitação (rate limited)
- `GET /api/v1/proposals` — lista (autenticado, papéis admin/editor/viewer)
- `GET /api/v1/proposals/<id>` — detalhe, já inclui `whatsapp_link` pronto
- `PATCH /api/v1/proposals/<id>/status` — atualiza status (com verificação
  de `version_id` para concorrência)
- `GET /api/v1/content/site` — conteúdo público do site (somente leitura)

Todas as respostas seguem o formato:

```json
{ "success": true, "data": { ... } }
```

ou, em erro:

```json
{ "error": "validation_error", "message": "...", "details": { ... } }
```
