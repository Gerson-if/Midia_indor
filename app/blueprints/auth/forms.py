from flask_wtf import FlaskForm
from wtforms import BooleanField, PasswordField, StringField
from wtforms.validators import DataRequired, Email, Length


class LoginForm(FlaskForm):
    email = StringField(
        "E-mail",
        validators=[DataRequired(message="Informe o e-mail."), Email(message="E-mail inválido.")],
    )
    password = PasswordField(
        "Senha",
        validators=[DataRequired(message="Informe a senha."), Length(min=6, max=128)],
    )
    remember_me = BooleanField("Manter conectado")
