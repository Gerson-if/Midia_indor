from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField
from wtforms import (
    BooleanField,
    FloatField,
    IntegerField,
    PasswordField,
    SelectField,
    StringField,
    TextAreaField,
)
from wtforms.validators import DataRequired, Email, Length, NumberRange, Optional

from app.models.proposal import ProposalStatus


class ProposalStatusForm(FlaskForm):
    status = SelectField(
        "Status",
        choices=[(s.value, s.value) for s in ProposalStatus],
        validators=[DataRequired()],
    )
    internal_notes = TextAreaField("Notas internas", validators=[Optional(), Length(max=2000)])
    version_id = IntegerField("version", validators=[Optional()])


class ServiceForm(FlaskForm):
    title = StringField("Título", validators=[DataRequired(), Length(max=120)])
    description = TextAreaField("Descrição", validators=[DataRequired(), Length(max=400)])
    display_order = IntegerField("Ordem", validators=[Optional(), NumberRange(min=0)], default=0)
    is_active = BooleanField("Ativo", default=True)
    image = FileField("Imagem", validators=[Optional(), FileAllowed(["jpg", "jpeg", "png", "webp", "gif"])])


class GalleryItemForm(FlaskForm):
    title = StringField("Título", validators=[DataRequired(), Length(max=120)])
    category = StringField("Categoria", validators=[DataRequired(), Length(max=80)])
    display_order = IntegerField("Ordem", validators=[Optional(), NumberRange(min=0)], default=0)
    is_active = BooleanField("Ativo", default=True)
    image = FileField("Imagem", validators=[Optional(), FileAllowed(["jpg", "jpeg", "png", "webp", "gif"])])


class TestimonialForm(FlaskForm):
    name = StringField("Nome", validators=[DataRequired(), Length(max=120)])
    company_name = StringField("Empresa", validators=[DataRequired(), Length(max=120)])
    text = TextAreaField("Depoimento", validators=[DataRequired(), Length(max=600)])
    display_order = IntegerField("Ordem", validators=[Optional(), NumberRange(min=0)], default=0)
    is_active = BooleanField("Ativo", default=True)


class PartnerForm(FlaskForm):
    name = StringField("Nome da marca", validators=[DataRequired(), Length(max=120)])
    display_order = IntegerField("Ordem", validators=[Optional(), NumberRange(min=0)], default=0)
    is_active = BooleanField("Ativo", default=True)
    logo = FileField("Logo", validators=[Optional(), FileAllowed(["jpg", "jpeg", "png", "webp", "gif"])])


class SiteSettingsForm(FlaskForm):
    company_name = StringField("Nome da empresa", validators=[DataRequired(), Length(max=120)])
    company_description = TextAreaField("Descrição", validators=[Optional(), Length(max=400)])
    company_whatsapp = StringField("WhatsApp (somente números, com DDI)", validators=[DataRequired(), Length(max=20)])
    company_email = StringField("E-mail", validators=[Optional(), Email(), Length(max=190)])
    company_phone = StringField("Telefone", validators=[Optional(), Length(max=30)])
    company_address = StringField("Endereço", validators=[Optional(), Length(max=255)])
    color_primary = StringField("Cor primária", validators=[DataRequired(), Length(max=9)])
    color_secondary = StringField("Cor secundária", validators=[DataRequired(), Length(max=9)])

    hero_title = StringField("Título do Hero", validators=[Optional(), Length(max=200)])
    hero_subtitle = TextAreaField("Subtítulo do Hero", validators=[Optional(), Length(max=400)])
    hero_overlay_opacity = FloatField("Opacidade do overlay", validators=[Optional(), NumberRange(min=0, max=1)])
    hero_cta_primary_label = StringField("Texto do botão principal", validators=[Optional(), Length(max=80)])
    hero_cta_secondary_label = StringField("Texto do botão secundário", validators=[Optional(), Length(max=80)])
    hero_video = FileField("Vídeo de fundo", validators=[Optional(), FileAllowed(["mp4", "webm"])])
    version_id = IntegerField("version", validators=[Optional()])


class UserForm(FlaskForm):
    name = StringField("Nome", validators=[DataRequired(), Length(max=120)])
    email = StringField("E-mail", validators=[DataRequired(), Email(), Length(max=190)])
    role = SelectField("Papel", choices=[("admin", "Administrador"), ("editor", "Editor"), ("viewer", "Visualizador")])
    is_active = BooleanField("Ativo", default=True)
    password = PasswordField(
        "Senha (deixe em branco para manter a atual)",
        validators=[Optional(), Length(min=8, max=128)],
    )
