# Deploy no Ubuntu (sem Docker)

Este diretório contém um instalador guiado para publicar o Nexo Mídia
numa VPS Ubuntu (22.04 ou 24.04) usando **Caddy + Gunicorn + systemd**,
sem depender de Docker. Layout simples, de **pasta única** — nada de
`releases/current/shared`: o código, o `.env`, o `venv` e os dados
(uploads, banco SQLite, logs) vivem todos dentro do mesmo diretório
(`/opt/midia-indoor` por padrão).

> **Nota:** o instalador guiado (`install.sh`) usa **Caddy** como proxy
> reverso — ele emite e renova HTTPS sozinho, sob demanda, para
> qualquer domínio apontado para a VPS (essencial no modo multi-página,
> onde o super admin cadastra domínios novos pelo painel sem reinstalar
> nada). Os scripts `setup-nginx.sh` / `generate-csr.sh` / `check-https.sh`
> continuam no projeto como um **caminho manual/avançado** (certificado
> autoassinado por IP sem domínio, certificado comprado via CSR, CA
> alternativa) — veja a seção 6.

> **Painel de controle:** depois de instalado, esqueça os caminhos dos
> scripts — rode só `sudo nexo`. É um menu interativo para atualizar,
> fazer backup, restaurar, migrar de servidor, reverter versão e rodar
> comandos do dia a dia (status, logs, firewall). Veja a seção 5.

```
deploy/
├── scripts/
│   ├── menu.sh            # "sudo nexo" — painel de controle interativo (ver seção 5)
│   ├── install.sh         # instalação inicial guiada (rodar 1x, usa Caddy)
│   ├── configure-env.sh   # assistente para (re)gerar o .env
│   ├── setup-caddy.sh     # gera/recarrega o Caddyfile (HTTPS automático)
│   ├── setup-nginx.sh     # [avançado/manual] config Nginx + HTTPS alternativo
│   ├── generate-csr.sh    # [avançado] chave privada + CSR p/ certificado comprado
│   ├── check-https.sh     # [avançado] diagnostica HTTPS no caminho Nginx
│   ├── update.sh          # publica uma atualização (git pull + migração)
│   ├── backup.sh          # backup completo: banco + uploads + metadados (.tar.gz)
│   ├── restore.sh         # restaura um pacote gerado pelo backup.sh
│   ├── migrate.sh         # assistente de migração para um servidor novo
│   ├── system.sh          # comandos rápidos: status, logs, reiniciar, firewall...
│   ├── rollback.sh        # volta para um commit anterior (git)
│   └── lib.sh             # funções internas (não executar direto)
├── Caddyfile.template              # template usado por setup-caddy.sh
├── nginx.conf.template             # [avançado] HTTP simples (sem HTTPS)
├── nginx-selfsigned.conf.template  # [avançado] HTTPS autoassinado (sem domínio)
├── nginx-letsencrypt.conf.template # [avançado] HTTPS com Let's Encrypt (Nginx)
├── nginx-custom.conf.template      # [avançado] HTTPS com certificado comprado via CSR
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
  tipo **A** do domínio para o IP da VPS *antes* de instalar — o
  instalador funciona sem isso, mas o Caddy só consegue emitir o
  certificado quando o domínio já resolve para o IP da VPS.
- **Sem domínio ainda?** Sem problema: o instalador roda normalmente e
  o site fica acessível por HTTP/IP. Quando tiver um domínio, rode
  `configure-env.sh` de novo para ativar o HTTPS automático. Se
  precisar de HTTPS **por IP mesmo sem domínio** (autoassinado), isso
  é possível pelo caminho manual/avançado com Nginx — veja a seção 6.

## 2. Instalação (rodar uma única vez)

Dentro da pasta do projeto, na VPS:

```bash
sudo bash deploy/scripts/install.sh
```

O script roda em 9 etapas (0 a 8), sempre com mensagens em português:

0. **Checagens prévias** — confere se é Ubuntu 22.04/24.04, se há
   espaço em disco suficiente, se a VPS tem internet, e se as portas
   80/443 já estão ocupadas por outro serviço (Apache, por exemplo).
   Qualquer problema aqui é sinalizado *antes* de mexer no sistema.
1. Pacotes do sistema (Python, PostgreSQL, Redis, Node.js — cada um
   opcional), com **3 tentativas automáticas** em cada instalação via
   `apt`/`curl`/`npm` (uma falha momentânea de rede/mirror não derruba
   a instalação inteira).
2–3. Usuário de sistema dedicado (`midia-indoor`) e cópia do código
   para o diretório escolhido.
4. `.env` gerado pelo assistente `configure-env.sh` — domínio ou IP,
   e-mail, WhatsApp e senhas são **validados na hora** (formato do
   e-mail, do domínio, tamanho mínimo de senha) em vez de só falhar
   silenciosamente mais tarde.
5–7. Dependências Python, build do Tailwind, migrações do banco,
   usuário administrador e permissões de arquivo.
8. Serviço systemd `midia-indoor` (Gunicorn) e HTTPS via **Caddy**.
   Diferente de só checar se o processo subiu, o instalador **testa de
   verdade** o endpoint `/healthz` antes de seguir para o Caddy — um
   erro de `.env`/banco/import é pego aqui, com uma mensagem clara, em
   vez de aparecer como um 502 confuso no navegador depois.

Ao final, a aplicação já está no ar, com:

- Serviço systemd `midia-indoor` rodando o Gunicorn (reinício automático
  em caso de falha) e validado via `/healthz` antes de prosseguir.
- **Caddy** configurado como proxy reverso com HTTPS automático — com
  domínio, o certificado Let's Encrypt é emitido e renovado sozinho, e
  o mesmo vale para qualquer domínio novo cadastrado depois pelo
  painel do super admin, sem precisar rodar nada de novo aqui. Sem
  domínio, o site fica em HTTP/IP até você configurar um.
- Firewall básico (UFW), se você optou por ativar — libera SSH, 80 e
  443.
- **Credenciais únicas por instalação**: `SECRET_KEY`, senha do banco
  e senha do administrador são geradas automaticamente (aleatórias,
  diferentes a cada VPS/cliente) sempre que você não informa nada —
  nunca reaproveitam um valor "de exemplo". Um resumo é salvo em
  `/root/midia-indoor-instalacao-<data>.txt` (permissão 600, só root
  lê) além de já estar no `.env`; vale apagar esse arquivo com
  `sudo shred -u` depois de guardar as senhas num lugar seguro.

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

## 5. Painel de controle: `sudo nexo`

O `install.sh` instala um comando global chamado `nexo`. A partir daí,
todo o resto deste guia (atualizar, reverter, comandos do dia a dia) —
mais backup completo, restauração e migração de servidor — está num
único menu interativo, sem precisar decorar caminho de script nenhum:

```bash
sudo nexo
```

```
 _   _                 __  __ _     _
| \ | | _____  _____  |  \/  (_) __| (_) __ _
|  \| |/ _ \ \/ / _ \ | |\/| | |/ _` | |/ _` |
| |\  |  __/>  < (_) || |  | | | (_| | | (_| |
|_| \_|\___/_/\_\___/ |_|  |_|_|\__,_|_|\__,_|
              painel de controle

? O que você quer fazer?
   1) Instalar (nova instalação, ou corrigir uma existente)
   2) Atualizar (publicar a última versão do código)
   3) Backup completo agora
   4) Listar backups
   5) Restaurar um backup
   6) Migrar para um servidor novo
   7) Reverter para uma versão de código anterior
   8) Comandos do sistema (status, logs, reiniciar, firewall...)
   9) Desinstalar
   10) Sair
```

Cada opção do menu é só uma porta de entrada para os scripts em
`deploy/scripts/` (que continuam funcionando sozinhos, direto pela
linha de comando, para quem preferir ou for automatizar via cron/CI).

### 5.1 Backup completo

```bash
sudo bash deploy/scripts/backup.sh /opt/midia-indoor "rotulo-opcional"
```

Gera um único `.tar.gz` autocontido em `/opt/midia-indoor/backups/full/`
com: dump do banco (SQLite copiado, ou PostgreSQL via `pg_dump --clean
--if-exists`, que se restaura sozinho em qualquer banco de destino),
as mídias enviadas (`app/static/uploads`), uma cópia do `.env` só como
referência, e um `manifest.json` (data, domínio, commit git, tipo de
banco). Mantém automaticamente os últimos 8 pacotes (configurável via
`NEXO_BACKUP_KEEP`), apagando os mais antigos.

### 5.2 Restaurar um backup

```bash
sudo bash deploy/scripts/restore.sh /opt/midia-indoor
# ou apontando direto um pacote específico:
sudo bash deploy/scripts/restore.sh /opt/midia-indoor /caminho/backup-....tar.gz
```

Mostra o conteúdo do pacote (manifesto) antes de mexer em qualquer
coisa, pede confirmação explícita, **sempre gera um backup de
segurança do estado atual antes de sobrescrever** (fica em
`backups/full/`, tag `pre-restore`) e só então substitui o banco e os
uploads. A pasta de uploads antiga é renomeada (não apagada) para
`uploads.antes-restore-<data>`. O `.env` do servidor **nunca** é
sobrescrito pela restauração — cada máquina mantém suas próprias
credenciais.

### 5.3 Migrar para um servidor novo

No servidor **antigo**:

```bash
sudo bash deploy/scripts/migrate.sh /opt/midia-indoor
```

Gera o backup completo e, se você já tiver acesso SSH ao servidor
novo, oferece enviar o pacote direto por `scp` — e mostra o passo a
passo exato para o servidor novo, que é sempre o mesmo fluxo de
sempre: `git clone` + `install.sh` (gera credenciais **próprias** do
servidor novo) + `restore.sh` (traz os dados do pacote). Depois só
apontar o DNS do domínio para o IP do servidor novo — o Caddy emite o
HTTPS automaticamente assim que propagar.

### 5.4 Comandos do sistema

Pelo menu (`sudo nexo` → "Comandos do sistema") ou direto:

```bash
sudo bash deploy/scripts/system.sh /opt/midia-indoor
```

Status dos serviços + healthcheck + versão do código, reiniciar,
recarregar sem downtime, logs em tempo real, uso de disco, ligar/
desligar o firewall (UFW) com as portas certas liberadas, e reabrir o
assistente de configuração do `.env` — tudo com confirmação antes de
qualquer ação que possa derrubar o site.

## 6. HTTPS por IP (sem domínio) e troca para Let's Encrypt depois — caminho manual/avançado com Nginx

> ⚠️ **Esta seção 6 inteira descreve o caminho manual/avançado com
> Nginx (`setup-nginx.sh`), não o que `install.sh` usa por padrão.**
> A instalação guiada usa Caddy (seção 2), que já emite HTTPS
> automaticamente sozinho quando você tem domínio, sem precisar rodar
> nada do que vem abaixo. Use esta seção só se precisar
> especificamente de: certificado autoassinado **sem** domínio, uma CA
> alternativa (ZeroSSL/Buypass) ou um certificado **comprado** via
> CSR — nesses três casos, o Caddy do fluxo padrão não cobre o
> cenário, e a alternativa é trocar para Nginx manualmente com os
> scripts abaixo.

### 6.1 Ativar HTTPS agora, só com o IP (certificado autoassinado)

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

### 6.2 Trocar para Let's Encrypt quando tiver domínio

Quando o domínio estiver pronto e apontando (registro DNS tipo A)
para o IP da VPS:

```bash
sudo bash deploy/scripts/configure-env.sh /opt/midia-indoor/.env
# escolha "Tenho um domínio" e ative o HTTPS quando perguntado
sudo bash deploy/scripts/setup-nginx.sh /opt/midia-indoor
```

O certificado autoassinado é automaticamente substituído pelo
certificado público do Let's Encrypt.

### 6.2b Let's Encrypt não funciona no seu provedor? Use ZeroSSL ou Buypass (também grátis)

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
partir para um certificado comprado via CSR (seção 6.3), que não
depende da porta 80 estar aberta.

### 6.3 Certificado comprado de uma CA (DigiCert etc.) via CSR

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

### 6.4 Como o HTTPS é mantido (e por que o cadeado não deveria sumir)

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

## 7. Comandos úteis do dia a dia

O mais simples é `sudo nexo` → "Comandos do sistema" (seção 5.4). Para
quem preferir digitar direto:

```bash
sudo systemctl status midia-indoor      # status da aplicação
sudo systemctl restart midia-indoor     # reiniciar
sudo journalctl -u midia-indoor -f      # logs da aplicação em tempo real
sudo nginx -t && sudo systemctl reload nginx   # validar/recarregar Nginx (só no caminho manual, seção 6)
curl -i http://127.0.0.1:8000/healthz   # testar a aplicação diretamente (sem Nginx/Caddy)
```

## 8. Solução de problemas comuns

- **`sudo journalctl -u midia-indoor -n 100`** — primeira coisa a olhar
  quando o serviço não sobe; mostra o erro real do Gunicorn/Flask.
- **Erro de `SECRET_KEY insegura` ou `DATABASE_URL é obrigatória`** — rode
  `configure-env.sh` novamente, algum valor ficou com o padrão de
  desenvolvimento.
- **`update.sh` falha com `fatal: detected dubious ownership in
  repository at '/opt/midia-indoor'`** — proteção do próprio Git quando
  o dono do diretório (dono dos arquivos no disco) é diferente do
  usuário que está rodando o comando (comum quando o `git pull` roda via
  `sudo`, como root, mas os arquivos pertencem ao usuário de serviço
  `midia-indoor`). Resolva liberando essa pasta como exceção e rode o
  update de novo:
  ```bash
  sudo git config --global --add safe.directory /opt/midia-indoor
  cd /opt/midia-indoor
  sudo bash deploy/scripts/update.sh
  ```
- **502 Bad Gateway no navegador** — o Nginx está de pé mas o Gunicorn
  não; veja `systemctl status midia-indoor` e os logs.
- **Certbot falhou ao emitir certificado** — confirme que o domínio já
  resolve (registro DNS tipo A) para o IP da VPS: `dig +short seudominio.com`.
  Depois rode `sudo bash deploy/scripts/setup-nginx.sh` de novo.
- **Certificado instalado, mas o navegador ainda mostra aviso/sem
  cadeado** — rode `sudo bash deploy/scripts/check-https.sh`; ele
  confere se o Nginx está servindo o certificado certo e se há
  conteúdo misto (`http://` numa página `https://`). Veja a seção 6.4.
- **Certificado comprado via CSR instalado, mas ainda com "x
  vermelho"/sem cadeado** — na grande maioria dos casos faltam os
  certificados **intermediários** da CA no arquivo instalado (só o
  certificado do domínio foi colocado). Veja a seção 6.3 e rode
  `check-https.sh`, que aponta exatamente isso.
- **Navegador avisa "conexão não é privada" ao acessar por IP** — normal
  quando o HTTPS está no modo autoassinado (sem domínio ainda); veja a
  seção 6.1. Não é um erro de configuração.
- **Porta 80/443 ocupada** — algo mais (Apache, outro Nginx) já está
  escutando; pare o outro serviço antes de instalar.

## Sobre o Docker

Esta versão do projeto usa apenas o deploy nativo descrito acima. Se
você tinha uma instalação anterior baseada em `docker-compose`, migre
para este fluxo: instale com `install.sh` (ele não interfere em
containers já existentes) e depois desative/remova os containers
antigos quando confirmar que a nova instalação está funcionando.
