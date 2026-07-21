#!/usr/bin/env bash
# =============================================================
# generate-csr.sh — gera a chave privada + o CSR (Certificate
# Signing Request) que qualquer autoridade certificadora paga
# (DigiCert, Sectigo, GoDaddy, etc.) pede para emitir um
# certificado SSL "manual" (fora do Let's Encrypt).
#
# O que este script faz:
#   1. Gera uma chave privada RSA 2048 bits (nunca sai deste
#      servidor — é ela que fica em __SSL_KEY__ no Nginx).
#   2. Gera o CSR a partir dessa chave, já com os domínios do
#      SERVER_NAMES do seu .env como Subject Alternative Names
#      (SAN) — hoje isso é exigido pela maioria das CAs e por
#      todos os navegadores modernos.
#   3. Mostra o conteúdo do CSR na tela e salva em disco, pronto
#      para colar no site da CA na hora de comprar/emitir o
#      certificado.
#
# O que você faz depois (fora deste script):
#   a) Cole o conteúdo do .csr no site da autoridade certificadora
#      (ex.: https://www.digicert.com/kb/csr-creation.htm explica
#      o processo do lado da CA).
#   b) Complete a validação que a CA pedir (e-mail, DNS ou arquivo
#      no servidor).
#   c) A CA devolve o certificado (.crt/.pem) + o(s) certificado(s)
#      intermediário(s) (chain/CA bundle). Junte tudo em um único
#      arquivo "fullchain" (seu certificado primeiro, depois os
#      intermediários) — é a causa nº 1 do cadeado não aparecer.
#   d) Rode: sudo deploy/scripts/configure-env.sh e escolha a opção
#      de certificado já comprado (SSL_MODE=custom), informando os
#      caminhos dos arquivos.
#   e) Rode: sudo deploy/scripts/setup-nginx.sh para ativar.
#
# Uso:
#   sudo deploy/scripts/generate-csr.sh [/opt/midia-indoor]
# =============================================================
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

need_cmd openssl

APP_DIR="${1:-/opt/midia-indoor}"
ENV_FILE="$APP_DIR/.env"
OUT_DIR="/etc/nginx/ssl/midia-indoor-csr"

title "Gerar chave privada + CSR para certificado SSL comprado"

# ---- Descobre o(s) domínio(s): do .env se existir, ou pergunta ----
DEFAULT_DOMAINS=""
if [ -f "$ENV_FILE" ]; then
    # shellcheck disable=SC1090
    source <(grep -E '^SERVER_NAMES=' "$ENV_FILE" | sed 's/^/export /') 2>/dev/null || true
    DEFAULT_DOMAINS="${SERVER_NAMES//\"/}"
fi

ask "Domínio principal (ex: meusite.com.br)" "$(echo "$DEFAULT_DOMAINS" | awk '{print $1}')" PRIMARY_DOMAIN
[ -z "$PRIMARY_DOMAIN" ] && die "É preciso informar um domínio — CAs não emitem certificado público para IP."

EXTRA_DOMAINS=""
if confirm "Incluir também 'www.$PRIMARY_DOMAIN' no mesmo certificado?" "s"; then
    EXTRA_DOMAINS="www.$PRIMARY_DOMAIN"
fi
ask "Outros domínios/subdomínios adicionais (separados por espaço, ou deixe em branco)" "$EXTRA_DOMAINS" ALL_EXTRA

ALL_DOMAINS="$PRIMARY_DOMAIN"
[ -n "$ALL_EXTRA" ] && ALL_DOMAINS="$PRIMARY_DOMAIN $ALL_EXTRA"

echo
info "Dados para o campo 'Subject' do CSR (a CA costuma pedir; capriche no razão social se for pessoa jurídica)."
ask "País (2 letras, ex: BR)" "BR" C_FIELD
ask "Estado" "" ST_FIELD
ask "Cidade" "" L_FIELD
ask "Razão social / nome (Organization)" "$PRIMARY_DOMAIN" O_FIELD
ask "Departamento (Organizational Unit, opcional)" "TI" OU_FIELD

mkdir -p "$OUT_DIR"
chmod 700 "$OUT_DIR"
TS="$(date -u +%Y%m%d%H%M%S)"
KEY_FILE="$OUT_DIR/${PRIMARY_DOMAIN}.key"
CSR_FILE="$OUT_DIR/${PRIMARY_DOMAIN}.csr"
CNF_FILE="$(mktemp)"

if [ -s "$KEY_FILE" ]; then
    warn "Já existe uma chave privada em $KEY_FILE."
    if ! confirm "Gerar uma NOVA chave (a antiga vai para .bak-$TS — qualquer CSR/certificado emitido com a antiga deixa de bater com a chave nova)?" "n"; then
        die "Mantendo a chave existente. Se só precisa reemitir o CSR com a mesma chave, isso não é suportado por este script — gere manualmente com 'openssl req -new -key $KEY_FILE ...'."
    fi
    cp -f "$KEY_FILE" "${KEY_FILE}.bak-$TS"
fi

# ---- Monta o SAN (Subject Alternative Name) com todos os domínios ----
SAN_ENTRIES=""
i=1
for d in $ALL_DOMAINS; do
    [ -n "$SAN_ENTRIES" ] && SAN_ENTRIES="$SAN_ENTRIES, "
    SAN_ENTRIES="${SAN_ENTRIES}DNS.${i}:${d}"
    i=$((i + 1))
done

cat >"$CNF_FILE" <<CNFEOF
[req]
default_bits       = 2048
prompt             = no
default_md         = sha256
distinguished_name = dn
req_extensions     = req_ext

[dn]
C  = ${C_FIELD}
ST = ${ST_FIELD}
L  = ${L_FIELD}
O  = ${O_FIELD}
OU = ${OU_FIELD}
CN = ${PRIMARY_DOMAIN}

[req_ext]
subjectAltName = @alt_names

[alt_names]
${SAN_ENTRIES//, /
}
CNFEOF

title "Gerando chave privada RSA 2048 e o CSR"
umask 077
openssl req -new -newkey rsa:2048 -nodes \
    -keyout "$KEY_FILE" \
    -out "$CSR_FILE" \
    -config "$CNF_FILE"
rm -f "$CNF_FILE"
chmod 600 "$KEY_FILE"
chmod 644 "$CSR_FILE"

ok "Chave privada salva em: $KEY_FILE (mantenha em segredo — NÃO envie para a CA nem para ninguém)"
ok "CSR salvo em:            $CSR_FILE"
echo
title "Conteúdo do CSR (copie tudo, incluindo as linhas BEGIN/END, e cole no site da CA)"
cat "$CSR_FILE"
echo
info "Conferência do que foi gerado:"
openssl req -in "$CSR_FILE" -noout -subject -ext subjectAltName 2>/dev/null | sed 's/^/  /'

echo
title "Próximos passos"
echo "  1) Compre/solicite o certificado na CA (ex.: DigiCert) e cole o"
echo "     conteúdo de $CSR_FILE quando pedirem o CSR."
echo "  2) Complete a validação de domínio que a CA exigir."
echo "  3) A CA vai te devolver o certificado do domínio e o(s)"
echo "     certificado(s) intermediário(s) (chain/CA bundle)."
echo "     -> Junte: SEU certificado + intermediário(s), NESSA ORDEM,"
echo "        em um único arquivo (isso é o 'fullchain'). Faltando o"
echo "        intermediário é a causa mais comum do navegador mostrar"
echo "        o domínio como não seguro mesmo com certificado instalado."
echo "  4) Rode: sudo deploy/scripts/configure-env.sh $ENV_FILE"
echo "     e escolha a opção de certificado já comprado, informando:"
echo "       - certificado + intermediários (fullchain): caminho no servidor"
echo "       - chave privada: $KEY_FILE"
echo "  5) Rode: sudo deploy/scripts/setup-nginx.sh $APP_DIR"
echo "  6) Confira o resultado com: sudo deploy/scripts/check-https.sh $APP_DIR"
