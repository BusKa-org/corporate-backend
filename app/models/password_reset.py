"""Password reset token for "forgot password" flow."""

from datetime import UTC, datetime

from sqlalchemy.dialects.postgresql import UUID

from .base import db


class PasswordResetToken(db.Model):
    __tablename__ = "password_reset_token"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("usuario.id", ondelete="CASCADE"),
        nullable=False,
    )
    token = db.Column(db.String(64), unique=True, nullable=False)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)

    def is_expired(self) -> bool:
        return datetime.now(UTC) >= self.expires_at
