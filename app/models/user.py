import enum
from datetime import datetime, timezone

from flask_login import UserMixin

from app.extensions import bcrypt, db


class UserRole(str, enum.Enum):
    ADMIN = "admin"       # acesso total, inclusive gerenciamento de usuários
    EDITOR = "editor"     # gerencia conteúdo e solicitações, sem gerenciar usuários
    VIEWER = "viewer"     # apenas visualização (somente leitura)


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(190), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(
        db.Enum(UserRole, name="user_role"), nullable=False, default=UserRole.EDITOR
    )
    is_active_flag = db.Column("is_active", db.Boolean, nullable=False, default=True)

    failed_login_attempts = db.Column(db.Integer, nullable=False, default=0)
    locked_until = db.Column(db.DateTime(timezone=True), nullable=True)
    last_login_at = db.Column(db.DateTime(timezone=True), nullable=True)
    last_login_ip = db.Column(db.String(45), nullable=True)

    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Otimistic locking: evita que duas edições concorrentes se sobrescrevam
    version_id = db.Column(db.Integer, nullable=False, default=1)
    __mapper_args__ = {"version_id_col": version_id}

    def set_password(self, raw_password: str) -> None:
        self.password_hash = bcrypt.generate_password_hash(raw_password).decode("utf-8")

    def check_password(self, raw_password: str) -> bool:
        if not self.password_hash:
            return False
        return bcrypt.check_password_hash(self.password_hash, raw_password)

    # ---- Flask-Login ----
    @property
    def is_active(self):
        return self.is_active_flag

    def get_id(self):
        return str(self.id)

    # ---- Autorização por papel ----
    def has_role(self, *roles) -> bool:
        role_values = {r.value if isinstance(r, UserRole) else r for r in roles}
        return self.role.value in role_values

    @property
    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN

    @property
    def is_locked(self) -> bool:
        if not self.locked_until:
            return False
        locked_until = self.locked_until
        if locked_until.tzinfo is None:
            # SQLite não preserva timezone ao persistir; assume-se UTC
            # (mesma convenção usada ao gravar o valor).
            locked_until = locked_until.replace(tzinfo=timezone.utc)
        return locked_until > datetime.now(timezone.utc)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "role": self.role.value,
            "is_active": self.is_active_flag,
            "last_login_at": self.last_login_at.isoformat() if self.last_login_at else None,
            "created_at": self.created_at.isoformat(),
        }

    def __repr__(self):
        return f"<User {self.email} ({self.role.value})>"
