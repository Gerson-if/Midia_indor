from datetime import datetime, timedelta, timezone

from flask import current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy.orm.exc import StaleDataError

from app.blueprints.auth import auth_bp
from app.blueprints.auth.forms import LoginForm
from app.extensions import db, limiter
from app.models import User
from app.utils.decorators import log_action

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15


def _commit_login_bookkeeping(user, apply_changes):
    """
    Aplica e commita alterações de bookkeeping no registro do usuário
    (contador de tentativas, bloqueio, último login) tolerando conflitos
    de concorrência otimista (User.version_id).

    Por que isso é necessário: é comum um mesmo usuário estar logando a
    partir de mais de uma aba/dispositivo ao mesmo tempo, ou o navegador
    reenviar a requisição de login após uma falha de rede — duas
    requisições concorrentes acabam tentando atualizar a MESMA linha de
    usuário quase simultaneamente. Como o modelo User usa controle de
    versão otimista, a segunda a commitar levanta StaleDataError. Sem
    tratamento, isso derrubava a requisição com um erro 500 ("Erro
    interno do servidor") bem no meio do fluxo de login — o tipo de
    "conflito de sessão"/erro de concorrência relatado. Aqui, se isso
    acontecer, recarregamos a linha mais recente do banco e tentamos
    aplicar a mudança uma única vez a mais antes de desistir; falhar
    silenciosamente é preferível a derrubar o login do usuário só por
    causa do bookkeeping (contador de tentativas, timestamps).
    """
    for attempt in range(2):
        try:
            apply_changes(user)
            db.session.commit()
            return
        except StaleDataError:
            db.session.rollback()
            current_app.logger.warning(
                "Conflito de concorrência ao atualizar o usuário %s durante login (tentativa %s).",
                getattr(user, "id", None),
                attempt + 1,
            )
            db.session.refresh(user)
    # Segunda tentativa também conflitou: não bloqueia o login por causa
    # disso, apenas segue sem persistir o bookkeeping desta vez.


@auth_bp.route("/login", methods=["GET", "POST"])
# Elevado de 10 para 20/min por IP: equipes acessando o painel a partir
# da mesma rede/escritório (mesmo IP público) compartilham essa cota.
# A defesa real contra força bruta é o bloqueio por CONTA (ver
# MAX_FAILED_ATTEMPTS/is_locked acima), não o limite por IP.
@limiter.limit("20 per minute", methods=["POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("admin.dashboard"))

    form = LoginForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        user = User.query.filter_by(email=email).first()

        if user and user.is_locked:
            flash("Conta temporariamente bloqueada por excesso de tentativas. Tente novamente mais tarde.", "danger")

            def _mark_blocked(u):
                log_action("auth.login_blocked", entity_type="User", entity_id=u.id)

            _commit_login_bookkeeping(user, _mark_blocked)
            return render_template("login.html", form=form)

        if user and user.is_active_flag and user.check_password(form.password.data):

            def _mark_success(u):
                u.failed_login_attempts = 0
                u.locked_until = None
                u.last_login_at = datetime.now(timezone.utc)
                u.last_login_ip = request.remote_addr
                log_action("auth.login_success", entity_type="User", entity_id=u.id)

            _commit_login_bookkeeping(user, _mark_success)

            login_user(user, remember=form.remember_me.data)
            next_url = request.args.get("next")
            # Evita "open redirect": só aceita caminhos internos relativos.
            if not next_url or not next_url.startswith("/"):
                next_url = url_for("admin.dashboard")
            return redirect(next_url)

        # Credenciais inválidas: incrementa contador de tentativas
        if user:

            def _mark_failed(u):
                u.failed_login_attempts = (u.failed_login_attempts or 0) + 1
                if u.failed_login_attempts >= MAX_FAILED_ATTEMPTS:
                    u.locked_until = datetime.now(timezone.utc) + timedelta(minutes=LOCKOUT_MINUTES)
                    log_action("auth.account_locked", entity_type="User", entity_id=u.id)
                log_action("auth.login_failed", entity_type="User", entity_id=u.id)

            _commit_login_bookkeeping(user, _mark_failed)
        else:
            current_app.logger.info("Tentativa de login com e-mail inexistente: %s", email)

        flash("E-mail ou senha incorretos.", "danger")

    return render_template("login.html", form=form)


@auth_bp.route("/logout")
@login_required
def logout():
    log_action("auth.logout", entity_type="User", entity_id=current_user.id)
    db.session.commit()
    logout_user()
    flash("Sessão encerrada com sucesso.", "info")
    return redirect(url_for("auth.login"))
