from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField
from wtforms.validators import DataRequired, Email, Length, Optional, Regexp


class ProposalRequestForm(FlaskForm):
    name = StringField(
        "Nome",
        validators=[DataRequired(message="Informe seu nome."), Length(min=2, max=150)],
    )
    email = StringField(
        "E-mail",
        validators=[DataRequired(message="Informe seu e-mail."), Email(message="E-mail inválido."), Length(max=190)],
    )
    phone = StringField(
        "Telefone/WhatsApp",
        validators=[
            DataRequired(message="Informe um telefone."),
            Regexp(r"^[0-9()+\-\s]{8,30}$", message="Telefone inválido."),
        ],
    )
    company_name = StringField("Empresa", validators=[Optional(), Length(max=150)])
    segment = StringField("Segmento", validators=[Optional(), Length(max=100)])
    preferred_locations = StringField("Locais de interesse", validators=[Optional(), Length(max=255)])
    budget_range = StringField("Faixa de investimento", validators=[Optional(), Length(max=60)])
    message = TextAreaField("Mensagem", validators=[Optional(), Length(max=2000)])

    # Honeypot anti-spam: campo invisível que humanos não preenchem.
    website = StringField("Website", validators=[Optional(), Length(max=0, message="Falha na validação.")])
