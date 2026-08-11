from flask_wtf import FlaskForm
from wtforms import BooleanField, PasswordField, SelectField, StringField, TextAreaField
from wtforms.validators import DataRequired, Email, Length, Optional, Regexp

from scripts.seed import TEMPLATE_CHOICES

SLUG_RE = Regexp(
    r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$",
    message="Use apenas letras minúsculas, números e hífen (ex.: cliente-xyz).",
)

# Aceita domínios e subdomínios (ex.: cliente.com, painel.cliente.com.br).
# Validação "boa o suficiente" no servidor -- o que realmente importa
# (o domínio resolver para esta VPS) só se confirma na prática, quando o
# DNS propaga e o Caddy consegue emitir o certificado sob demanda.
DOMAIN_RE = Regexp(
    r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$",
    message="Informe um domínio válido, ex.: cliente.com.br ou painel.cliente.com.",
)


class TenantCreateForm(FlaskForm):
    name = StringField("Nome da página/cliente", validators=[DataRequired(), Length(max=120)])
    slug = StringField(
        "Identificador interno (opcional)",
        validators=[Optional(), Length(max=140), SLUG_RE],
        description="Só aparece no seu painel. Deixe em branco para gerar automaticamente.",
    )
    domain = StringField(
        "Domínio inicial (opcional)",
        validators=[Optional(), Length(max=255), DOMAIN_RE],
        description="Pode ser adicionado depois. Ex.: cliente.com.br",
    )

    owner_name = StringField("Nome do administrador", validators=[DataRequired(), Length(max=120)])
    owner_email = StringField("E-mail do administrador", validators=[DataRequired(), Email(), Length(max=190)])
    owner_password = PasswordField("Senha inicial", validators=[DataRequired(), Length(min=8, max=128)])

    template = SelectField(
        "Modelo de conteúdo inicial",
        choices=TEMPLATE_CHOICES,
        default="midia_indoor",
        description="A página já abre com textos, serviços e depoimentos de exemplo prontos para adaptar, de acordo com o tipo de negócio escolhido.",
    )


class TenantDomainForm(FlaskForm):
    domain = StringField("Domínio ou subdomínio", validators=[DataRequired(), Length(max=255), DOMAIN_RE])
    is_primary = BooleanField("Definir como domínio principal", default=False)


class TenantBlockForm(FlaskForm):
    reason = TextAreaField(
        "Motivo do bloqueio (interno)",
        validators=[DataRequired(), Length(max=300)],
        description="Visível só para você e para o administrador desta página -- nunca para o visitante final.",
    )


class TenantDeleteForm(FlaskForm):
    confirm_slug = StringField(
        "Digite o identificador da página para confirmar",
        validators=[DataRequired(), Length(max=140)],
    )
