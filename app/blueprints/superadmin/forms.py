from flask_wtf import FlaskForm
from wtforms import BooleanField, DateField, DecimalField, PasswordField, SelectField, StringField, TextAreaField
from wtforms.validators import DataRequired, Email, Length, NumberRange, Optional, Regexp

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


class InvoiceCreateForm(FlaskForm):
    title = StringField(
        "Título da fatura", validators=[DataRequired(), Length(max=150)], description="Ex.: Mensalidade Agosto/2026"
    )
    due_date = DateField("Data de vencimento", validators=[DataRequired()])
    is_recurring = BooleanField(
        "Cobrança recorrente (renova a cada período, ex.: mensalidade)", default=False
    )
    service_cutoff_at = DateField(
        "Data de desligamento total do serviço (opcional)",
        validators=[Optional()],
        description=(
            "Se não for paga até esta data, o acesso é encerrado por completo (ex.: fornecedor "
            "externo de hospedagem corta o serviço) -- diferente de \"bloquear\", que só tira o "
            "site público do ar mantendo o painel acessível. Avisado ao admin da página."
        ),
    )
    notes = TextAreaField("Observações (opcional)", validators=[Optional(), Length(max=1000)])


class ChangeTemplateForm(FlaskForm):
    template = SelectField(
        "Novo modelo de conteúdo",
        choices=[c for c in TEMPLATE_CHOICES if c[0] != "none"],
        description=(
            "Substitui os serviços, galeria, depoimentos e parceiros atuais da página pelos do modelo "
            "escolhido. Textos do Hero e páginas legais só são preenchidos se ainda estiverem vazios -- "
            "o que o cliente já personalizou de verdade não é apagado."
        ),
    )


class InvoiceItemForm(FlaskForm):
    description = StringField("Descrição do item", validators=[DataRequired(), Length(max=200)])
    amount = DecimalField(
        "Valor (R$)", validators=[DataRequired(), NumberRange(min=0.01)], places=2
    )
