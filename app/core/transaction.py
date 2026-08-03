from contextlib import contextmanager

from sqlalchemy.exc import IntegrityError

from app.core.exceptions import ConflictError
from app.models.base import db


@contextmanager
def transactional():
    try:
        yield
        db.session.commit()
    except IntegrityError as e:
        db.session.rollback()
        # You can parse e.orig / constraint name if you want finer codes
        raise ConflictError("Violação de integridade") from e
    except Exception:
        db.session.rollback()
        raise
