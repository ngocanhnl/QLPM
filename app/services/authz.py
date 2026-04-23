from functools import wraps

from flask import abort
from flask_login import current_user

from app.models.enums import UserRole


def roles_required(*roles: UserRole):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                abort(401)
            # ADMIN has full access to all RBAC-protected endpoints.
            if current_user.role == UserRole.ADMIN:
                return fn(*args, **kwargs)
            if current_user.role not in roles:
                abort(403)
            return fn(*args, **kwargs)

        return wrapper

    return decorator

