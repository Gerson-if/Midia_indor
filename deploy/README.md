# Deploy no Ubuntu (sem Docker)

Este diretório contém um instalador guiado para publicar o Nexo Mídia
numa VPS Ubuntu (22.04 ou 24.04) usando **Nginx + Gunicorn + systemd**,
sem depender de Docker. Os scripts fazem perguntas simples (domínio ou
IP? PostgreSQL ou SQLite? etc.) e configuram tudo sozinhos.

```
deploy/
├── scripts/
│   ├── install.sh        # instalação inicial guiada (rodar 1x)
│   ├── configure-env.sh  # assistente para (re)gerar o .env
│   ├── setup-nginx.sh    # gera/atualiza a config do Nginx (+ HTTPS)
│   ├── update.sh         # publica uma atualização com segurança
│   ├── rollback.sh       # volta manualmente para a versão anterior
│   └── lib.sh            # funções internas (não executar direto)
├── nginx.conf.template   # modelo usado pelo setup-nginx.sh
├── midia-indoor.service  # unit do systemd instalada pelo install.sh
└── gunicorn.conf.py      # configuração do Gunicorn
```

## 1. Pré-requisitos

- Uma VPS Ubuntu 22.04/24.04 nova (ou limpa), com acesso `sudo`.
- O código do projeto na VPS. Duas formas simples:
  - **Git (recomendado)**, porque facilita atualizações depois:
    ```bash
    git clone <url-do-seu-repositorio> midia-indoor
    cd midia-indoor
    ```
  - **Upload manual** (zip): envie o `.zip` do projeto para a VPS
    (`scp`, WinSCP, etc.), depois:
    ```bash
    unzip Midia_indor-main.zip
    cd Midia_indor-main
    ```
- (Opcional) Se for usar domínio com HTTPS, aponte o registro DNS
  tipo **A** do domínio para o IP da VPS *antes* de instalar.

## 2. Instalação (rodar uma única vez)

Dentro da pasta do projeto, na VPS:

```bash
sudo bash deploy/scripts/install.sh
```

O script vai perguntar, em português, passo a passo:

1. Em qual pasta instalar (padrão `/opt/midia-indoor`).
2. Quais pacotes de sistema instalar (PostgreSQL, Redis, Certbot, Node.js
   para build do Tailwind — cada um opcional, com sugestão padrão).
3. **Domínio ou apenas IP da VPS** — se você tiver domínio, ativa HTTPS
   automático via Let's Encrypt; se ainda não tiver, o site sobe em HTTP
   pelo IP e você pode ativar HTTPS depois (veja a seção 5).
4. Banco de dados: PostgreSQL (cria o banco/usuário sozinho) ou SQLite.
5. Dados da empresa (nome, WhatsApp, e-mail, telefone, endereço) que
   aparecem no site.
6. Dados do administrador inicial (pode gerar uma senha forte sozinho).

Ao final, a aplicação já está no ar, com:

- Serviço systemd `midia-indoor` rodando o Gunicorn (reinício automático
  em caso de falha).
- Nginx configurado como proxy reverso, servindo `/static` diretamente.
- HTTPS ativo (se você escolheu domínio) com renovação automática.
- Firewall básico (UFW) liberando apenas SSH, HTTP e HTTPS (opcional).

Estrutura criada em `/opt/midia-indoor`:

```
/opt/midia-indoor/
├── current -> releases/20260720231500/   # versão em produção (symlink)
├── releases/                             # cada versão publicada
└── shared/
    ├── .env         # variáveis de ambiente (preservado entre updates)
    ├── venv/        # ambiente virtual Python (preservado)
    ├── uploads/     # mídias enviadas pelo painel (preservado)
    ├── instance/    # banco SQLite, se usado (preservado)
    ├── logs/        # logs da aplicação (preservado)
    └── backups/     # backups automáticos gerados pelo update.sh
```

Rodar `install.sh` de novo é seguro (idempotente): ele cria uma nova
release e reaproveita o `.env`/banco/uploads já existentes se você
mantiver as respostas.

## 3. Publicando atualizações com segurança

Sempre que tiver uma nova versão do código (novo `git pull` ou um novo
`.zip` extraído), rode, de dentro da pasta com o código novo:

```bash
sudo bash deploy/scripts/update.sh
```

O que o `update.sh` faz, nessa ordem:

1. **Backup** automático do banco de dados (SQLite ou `pg_dump` do
   PostgreSQL) e do `.env`, salvos em `shared/backups/`.
2. Publica o novo código numa **release separada**, sem tocar na versão
   que está no ar.
3. Instala as dependências Python novas/atualizadas e (se houver
   `package.json`) reconstrói os assets do Tailwind.
4. Roda as **migrações do banco** (`flask db upgrade`). Se falhar, o
   script para aqui — a versão em produção **não é alterada**.
5. Troca o `current` para a nova release e reinicia o serviço.
6. Confere o endpoint `/healthz`. Se a nova versão não responder
   corretamente, o script **reverte sozinho** para a versão anterior e
   reinicia — o site nunca fica no ar quebrado.
7. Mantém as 5 releases mais recentes e apaga as mais antigas.

Para automação (ex.: um hook de CI que faz `ssh` na VPS), pule as
confirmações interativas com:

```bash
sudo AUTO_YES=1 bash deploy/scripts/update.sh
```

### Reverter manualmente

Se perceber um problema depois que tudo parecia OK, escolha entre as
releases publicadas:

```bash
sudo bash deploy/scripts/rollback.sh
```

## 4. Reconfigurar variáveis de ambiente depois

Para trocar domínio, senha, dados da empresa, etc. sem reinstalar tudo:

```bash
sudo bash deploy/scripts/configure-env.sh /opt/midia-indoor/shared/.env
sudo systemctl restart midia-indoor
```

## 5. Ativar HTTPS depois (se instalou só com IP)

Quando o domínio estiver pronto e apontando para o IP da VPS:

```bash
sudo bash deploy/scripts/configure-env.sh /opt/midia-indoor/shared/.env
# escolha "Tenho um domínio" e ative o HTTPS quando perguntado
sudo bash deploy/scripts/setup-nginx.sh /opt/midia-indoor
```

## 6. Comandos úteis do dia a dia

```bash
sudo systemctl status midia-indoor      # status da aplicação
sudo systemctl restart midia-indoor     # reiniciar
sudo journalctl -u midia-indoor -f      # logs da aplicação em tempo real
sudo nginx -t && sudo systemctl reload nginx   # validar/recarregar Nginx
curl -i http://127.0.0.1:8000/healthz   # testar a aplicação diretamente (sem Nginx)
```

## 7. Solução de problemas comuns

- **`sudo journalctl -u midia-indoor -n 100`** — primeira coisa a olhar
  quando o serviço não sobe; mostra o erro real do Gunicorn/Flask.
- **Erro de `SECRET_KEY insegura` ou `DATABASE_URL é obrigatória`** — rode
  `configure-env.sh` novamente, algum valor ficou com o padrão de
  desenvolvimento.
- **502 Bad Gateway no navegador** — o Nginx está de pé mas o Gunicorn
  não; veja `systemctl status midia-indoor` e os logs.
- **Certbot falhou ao emitir certificado** — confirme que o domínio já
  resolve (registro DNS tipo A) para o IP da VPS: `dig +short seudominio.com`.
  Depois rode `sudo bash deploy/scripts/setup-nginx.sh` de novo.
- **Porta 80/443 ocupada** — algo mais (Apache, outro Nginx) já está
  escutando; pare o outro serviço antes de instalar.

## Sobre o Docker

Esta versão do projeto usa apenas o deploy nativo descrito acima. Se
você tinha uma instalação anterior baseada em `docker-compose`, migre
para este fluxo: instale com `install.sh` (ele não interfere em
containers já existentes) e depois desative/remova os containers
antigos quando confirmar que a nova instalação está funcionando.
