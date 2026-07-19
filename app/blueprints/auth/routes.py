from datetime import datetime, timedelta, timezone

from flask import current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from app.blueprints.auth import auth_bp
from app.blueprints.auth.forms import LoginForm
from app.extensions import db, limiter
from app.models import User
from app.utils.decorators import log_action

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15


@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("admin.dashboard"))

    form = LoginForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        user = User.query.filter_by(email=email).first()

        if user and user.is_locked:
            flash("Conta temporariamente bloqueada por excesso de tentativas. Tente novamente mais tarde.", "danger")
            log_action("auth.login_blocked", entity_type="User", entity_id=user.id)
            db.session.commit()
            return render_template("login.html", form=form)

        if user and user.is_active_flag and user.check_password(form.password.data):
            user.failed_login_attempts = 0
            user.locked_until = None
            user.last_login_at = datetime.now(timezone.utc)
            user.last_login_ip = request.remote_addr
            log_action("auth.login_success", entity_type="User", entity_id=user.id)
            db.session.commit()

            login_user(user, remember=form.remember_me.data)
            next_url = request.args.get("next")
            # Evita "open redirect": só aceita caminhos internos relativos.
            if not next_url or not next_url.startswith("/"):
                next_url = url_for("admin.dashboard")
            return redirect(next_url)

        # Credenciais inválidas: incrementa contador de tentativas
        if user:
            user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
            if user.failed_login_attempts >= MAX_FAILED_ATTEMPTS:
                user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=LOCKOUT_MINUTES)
                log_action("auth.account_locked", entity_type="User", entity_id=user.id)
            log_action("auth.login_failed", entity_type="User", entity_id=user.id)
            db.session.commit()
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
