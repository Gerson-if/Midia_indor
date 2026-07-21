# Deploy no Ubuntu (sem Docker)

Este diretório contém um instalador guiado para publicar o Nexo Mídia
numa VPS Ubuntu (22.04 ou 24.04) usando **Nginx + Gunicorn + systemd**,
sem depender de Docker. Layout simples, de **pasta única** — nada de
`releases/current/shared`: o código, o `.env`, o `venv` e os dados
(uploads, banco SQLite, logs) vivem todos dentro do mesmo diretório
(`/opt/midia-indoor` por padrão).

```
deploy/
├── scripts/
│   ├── install.sh        # instalação inicial guiada (rodar 1x)
│   ├── configure-env.sh  # assistente para (re)gerar o .env
│   ├── setup-nginx.sh    # gera/atualiza a config do Nginx (+ HTTPS)
│   ├── generate-csr.sh   # gera chave privada + CSR p/ certificado comprado
│   ├── check-https.sh    # diagnostica o estado do HTTPS/certificado
│   ├── update.sh         # publica uma atualização (git pull + migração)
│   ├── rollback.sh       # volta para um commit anterior (git)
│   └── lib.sh            # funções internas (não executar direto)
├── nginx.conf.template            # HTTP simples (sem HTTPS)
├── nginx-selfsigned.conf.template # HTTPS autoassinado (sem domínio)
├── nginx-letsencrypt.conf.template# HTTPS com Let's Encrypt (com domínio)
├── nginx-custom.conf.template     # HTTPS com certificado comprado via CSR
├── midia-indoor.service  # unit do systemd instalada pelo install.sh
└── gunicorn.conf.py      # configuração do Gunicorn
```

## 1. Pré-requisitos

- Uma VPS Ubuntu 22.04/24.04 nova (ou limpa), com acesso `sudo`.
- O código do projeto na VPS. **Recomendado: Git** — deixa as
  atualizações depois muito mais simples (`git pull`):
  ```bash
  git clone <url-do-seu-repositorio> midia-indoor
  cd midia-indoor
  ```
  Sem Git também funciona (upload manual de `.zip`), só que as
  atualizações passam a ser via `rsync` em vez de `git pull` —
  veja a seção 3.
- (Opcional) Se for usar domínio com HTTPS, aponte o registro DNS
  tipo **A** do domínio para o IP da VPS *antes* de instalar.
- **Sem domínio ainda?** Sem problema: o instalador oferece HTTPS
  mesmo assim, por IP, usando um **certificado autoassinado** (gerado
  localmente com `openssl`, sem depender de nenhum serviço externo).
  A conexão fica criptografada normalmente; a única diferença é que o
  navegador mostra um aviso de segurança na primeira visita, porque
  não existe domínio para validar com uma autoridade certificadora
  pública (Let's Encrypt exige domínio). Veja a seção 5.

## 2. Instalação (rodar uma única vez)

Dentro da pasta do projeto, na VPS:

```bash
sudo bash deploy/scripts/install.sh
```

O script vai perguntar, em português, passo a passo: onde instalar
(padrão `/opt/midia-indoor`), quais pacotes de sistema instalar
(PostgreSQL, Redis, Certbot, Node.js — cada um opcional), domínio ou
IP, banco de dados, dados da empresa e dados do administrador inicial.

Ao final, a aplicação já está no ar, com:

- Serviço systemd `midia-indoor` rodando o Gunicorn (reinício automático
  em caso de falha).
- Nginx configurado como proxy reverso, servindo `/static` diretamente.
- HTTPS ativo, de duas formas possíveis:
  - **Com domínio:** certificado público via Let's Encrypt, com
    renovação automática.
  - **Só com IP (sem domínio):** certificado autoassinado gerado
    localmente, se você optar por ativar HTTPS mesmo assim (o
    instalador pergunta). O navegador mostra um aviso de segurança na
    primeira visita — é o esperado, a conexão continua criptografada.
- Firewall básico (UFW), se você optou por ativar — libera SSH, 80 e
  443.

Estrutura criada (pasta única, sem symlinks):

```
/opt/midia-indoor/
├── venv/                  # ambiente virtual Python (preservado nos updates)
├── .env                   # variáveis de ambiente (preservado)
├── app/static/uploads/    # mídias enviadas pelo painel (preservado)
├── instance/              # banco SQLite, se usado (preservado)
├── logs/                  # logs da aplicação (preservado)
├── backups/               # backups automáticos gerados pelo update.sh
└── (todo o resto do código da aplicação)
```

`venv/`, `.env`, `instance/`, `logs/` e `app/static/uploads/` já estão
no `.gitignore` do projeto — por isso um `git pull` nunca sobrescreve
esses dados.

Rodar `install.sh` de novo é seguro (idempotente).

## 3. Publicando atualizações

**Com Git (recomendado)** — direto na VPS, dentro de `/opt/midia-indoor`:

```bash
cd /opt/midia-indoor
sudo bash deploy/scripts/update.sh
```

**Sem Git (zip)** — envie o novo código pra VPS e rode de dentro da
pasta extraída:

```bash
sudo bash deploy/scripts/update.sh /opt/midia-indoor
```

O que o `update.sh` faz, nessa ordem:

1. **Backup** rápido do banco (SQLite ou `pg_dump` do PostgreSQL) e
   do `.env`, salvos em `/opt/midia-indoor/backups/`.
2. Publica o código novo (`git pull` ou `rsync`, preservando
   venv/.env/uploads/logs/instance).
3. Instala as dependências Python novas/atualizadas e (se houver
   `package.json`) reconstrói os assets do Tailwind.
4. Roda as **migrações do banco** (`flask db upgrade`). Se falhar, o
   script para aqui e **não reinicia o serviço**.
5. Reinicia o serviço e confere o endpoint `/healthz`.
6. Se a nova versão não responder e o deploy foi via Git, o script
   **reverte sozinho** (`git reset --hard` para o commit anterior) e
   reinicia — o site nunca fica no ar quebrado. Sem Git, o backup do
   passo 1 fica disponível para restauração manual.

### Reverter manualmente

```bash
sudo bash deploy/scripts/rollback.sh
```
Mostra os últimos commits e pede qual deles ativar (só funciona em
instalações com Git — sem Git, restaure pelo backup em `backups/`).

## 4. Reconfigurar variáveis de ambiente depois

Para trocar domínio, senha, dados da empresa, etc. sem reinstalar tudo:

```bash
sudo bash deploy/scripts/configure-env.sh /opt/midia-indoor/.env
sudo systemctl restart midia-indoor
```

## 5. HTTPS por IP (sem domínio) e troca para Let's Encrypt depois

### 5.1 Ativar HTTPS agora, só com o IP (certificado autoassinado)

Se ainda não tem domínio, o instalador já pergunta se quer ativar
HTTPS autoassinado (recomendado — deixa o painel de admin
criptografado mesmo sem domínio). Se pulou essa opção ou quer
ativar/desativar depois:

```bash
sudo bash deploy/scripts/configure-env.sh /opt/midia-indoor/.env
# escolha "Vou usar apenas o IP da VPS" e confirme o HTTPS autoassinado
sudo bash deploy/scripts/setup-nginx.sh /opt/midia-indoor
```

Isso deixa o site acessível em `https://SEU-IP/`. Como não existe
domínio para validar com uma autoridade certificadora pública
(Let's Encrypt exige domínio), o navegador mostra um aviso do tipo
"a conexão não é privada" na primeira visita — clique em
"avançado" → "continuar mesmo assim". A conexão continua
criptografada normalmente; o aviso é só porque o certificado não é
assinado por uma CA pública. O certificado é gerado uma única vez em
`/etc/nginx/ssl/midia-indoor/` e reaproveitado nas próximas execuções
do `setup-nginx.sh` (não é regerado a cada `update.sh`).

Se quiser eliminar o aviso do navegador enquanto não tem domínio,
importe o arquivo `/etc/nginx/ssl/midia-indoor/fullchain.pem` como
certificado confiável nos dispositivos que acessam o painel (opcional,
não é necessário para o site funcionar).

### 5.2 Trocar para Let's Encrypt quando tiver domínio

Quando o domínio estiver pronto e apontando (registro DNS tipo A)
para o IP da VPS:

```bash
sudo bash deploy/scripts/configure-env.sh /opt/midia-indoor/.env
# escolha "Tenho um domínio" e ative o HTTPS quando perguntado
sudo bash deploy/scripts/setup-nginx.sh /opt/midia-indoor
```

O certificado autoassinado é automaticamente substituído pelo
certificado público do Let's Encrypt.

### 5.2b Let's Encrypt não funciona no seu provedor? Use ZeroSSL ou Buypass (também grátis)

Alguns provedores/hostings bloqueiam a porta 80 por padrão, e isso faz
a emissão do Let's Encrypt falhar mesmo com o domínio configurado
corretamente. Se for esse o seu caso, o projeto tem uma segunda opção
de CA **igualmente gratuita e automática** (emite e renova sozinha),
usando o [acme.sh](https://github.com/acmesh-official/acme.sh) por
baixo dos panos:

```bash
sudo bash deploy/scripts/configure-env.sh /opt/midia-indoor/.env
# escolha "Tenho um domínio" -> "Outra CA grátis automática — ZeroSSL/Buypass"
# e depois ZeroSSL ou Buypass
sudo bash deploy/scripts/setup-nginx.sh /opt/midia-indoor
```

Na primeira vez, o `setup-nginx.sh` instala o `acme.sh` sozinho (clona
de `github.com/acmesh-official/acme.sh`), emite o certificado pela CA
escolhida e já deixa a renovação automática configurada (cron próprio
do `acme.sh` — não depende do `certbot.timer`). Se a emissão falhar, o
script mostra o log e o diagnóstico da causa mais provável, do mesmo
jeito que já faz para o Let's Encrypt.

Importante: se a causa da falha do Let's Encrypt for **porta 80
bloqueada pelo provedor**, trocar de CA não resolve sozinho — todas
essas CAs gratuitas automáticas validam por HTTP na porta 80. Nesse
caso, a saída é usar a Cloudflare na frente do domínio (grátis) ou
partir para um certificado comprado via CSR (seção 5.3), que não
depende da porta 80 estar aberta.

### 5.3 Certificado comprado de uma CA (DigiCert etc.) via CSR

Se preferir (ou precisar, por política interna/compliance) usar um
certificado pago em vez do Let's Encrypt, o fluxo é:

```bash
# 1) Gera a chave privada + o CSR (Certificate Signing Request)
sudo bash deploy/scripts/generate-csr.sh /opt/midia-indoor
```

O script pede o domínio e os dados da empresa e devolve o conteúdo do
CSR na tela — copie e cole no site da CA na hora de comprar/emitir o
certificado (veja o guia da própria CA, ex.:
https://www.digicert.com/kb/csr-creation.htm). A chave privada fica
salva em `/etc/nginx/ssl/midia-indoor-csr/` e **nunca deve ser
enviada** para a CA nem para ninguém — só o CSR.

Depois que a CA validar o domínio e emitir o certificado, ela devolve
dois tipos de arquivo: o certificado do seu domínio e o(s)
certificado(s) **intermediário(s)** (às vezes chamado de "CA bundle"
ou "chain"). Junte na configuração:

```bash
sudo bash deploy/scripts/configure-env.sh /opt/midia-indoor/.env
# escolha "Tenho um domínio" -> "Já tenho/vou comprar um certificado... (CSR)"
# informe os caminhos do certificado, da chave e dos intermediários
sudo bash deploy/scripts/setup-nginx.sh /opt/midia-indoor
```

O `setup-nginx.sh` confere automaticamente as causas mais comuns do
**"x vermelho" / cadeado ausente mesmo com certificado instalado**:

- a chave privada não bate com o certificado;
- faltam os certificados intermediários da CA (o motivo mais comum —
  sem eles o navegador não consegue montar a cadeia de confiança até
  a raiz, mesmo com o certificado do domínio correto e válido);
- o certificado não cobre o domínio acessado (campo SAN);
- o certificado está expirado ou perto de vencer.

Ao final, rode `sudo bash deploy/scripts/check-https.sh /opt/midia-indoor`
para uma validação completa da cadeia (o mesmo tipo de checagem que o
navegador faz). Diferente do Let's Encrypt, **este modo não renova
sozinho** — quando a CA emitir a renovação, rode `configure-env.sh` +
`setup-nginx.sh` novamente com os novos arquivos.

### 5.4 Como o HTTPS é mantido (e por que o cadeado não deveria sumir)

Desde esta versão, o `setup-nginx.sh` **não deixa mais o Certbot editar
o `nginx.conf` diretamente** (não usamos `certbot --nginx`). O Certbot
só cuida de emitir/renovar o certificado; quem monta o bloco HTTPS do
Nginx é o nosso próprio template (`nginx-letsencrypt.conf.template`),
sempre reaplicado. Isso evita o problema mais comum de projetos assim:
rodar o script de novo e ele apagar sem querer o bloco SSL que o
Certbot tinha inserido, fazendo o cadeado sumir mesmo com um
certificado válido em disco.

Além disso, toda alteração no vhost é feita com backup automático: se
a nova configuração não passar em `nginx -t`, a anterior (que estava
funcionando) é restaurada e o site não fica fora do ar.

Se mesmo assim o navegador mostrar o domínio como "não totalmente
seguro" com um certificado instalado, rode:

```bash
sudo bash deploy/scripts/check-https.sh /opt/midia-indoor
```

Esse comando confere, entre outras coisas, se o Nginx está servindo
**exatamente** o certificado que está em disco (o motivo mais comum
do aviso persistir) e se há algum recurso carregado em `http://` numa
página `https://` (conteúdo misto). Depois de corrigir qualquer coisa
no servidor, vale também testar em uma aba anônima do navegador, já
que uma visita anterior por HTTP ou com um certificado antigo pode ter
ficado em cache localmente.

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
- **Certificado instalado, mas o navegador ainda mostra aviso/sem
  cadeado** — rode `sudo bash deploy/scripts/check-https.sh`; ele
  confere se o Nginx está servindo o certificado certo e se há
  conteúdo misto (`http://` numa página `https://`). Veja a seção 5.4.
- **Certificado comprado via CSR instalado, mas ainda com "x
  vermelho"/sem cadeado** — na grande maioria dos casos faltam os
  certificados **intermediários** da CA no arquivo instalado (só o
  certificado do domínio foi colocado). Veja a seção 5.3 e rode
  `check-https.sh`, que aponta exatamente isso.
- **Navegador avisa "conexão não é privada" ao acessar por IP** — normal
  quando o HTTPS está no modo autoassinado (sem domínio ainda); veja a
  seção 5.1. Não é um erro de configuração.
- **Porta 80/443 ocupada** — algo mais (Apache, outro Nginx) já está
  escutando; pare o outro serviço antes de instalar.

## Sobre o Docker

Esta versão do projeto usa apenas o deploy nativo descrito acima. Se
você tinha uma instalação anterior baseada em `docker-compose`, migre
para este fluxo: instale com `install.sh` (ele não interfere em
containers já existentes) e depois desative/remova os containers
antigos quando confirmar que a nova instalação está funcionando.
