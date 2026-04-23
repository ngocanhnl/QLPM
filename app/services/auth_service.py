from flask_login import login_user, logout_user

from app.extensions import db
from app.models.doctor import Doctor
from app.models.hospital import Hospital
from app.models.enums import UserRole
from app.models.user import User


class AuthService:
    @staticmethod
    def register_user(
        *,
        username: str,
        email: str,
        phone: str,
        password: str,
        role: UserRole,
        specialty: str | None = None,
        hospital_id: int | None = None,
        description: str | None = None,
        experience_years: int | None = None,
    ) -> User:
        user = User(
            username=username,
            email=(email or "").strip(),
            phone=(phone or "").strip(),
            role=role,
        )
        user.set_password(password)
        db.session.add(user)
        db.session.flush()

        if role == UserRole.DOCTOR:
            if not specialty:
                raise ValueError("Specialty is required for DOCTOR")
            if not hospital_id:
                raise ValueError("Hospital selection is required for DOCTOR")
            hospital = db.session.get(Hospital, int(hospital_id))
            if not hospital:
                raise ValueError("Selected hospital does not exist")
            doc = Doctor(
                user_id=user.id,
                specialty=specialty.strip(),
                hospital_id=hospital.id,
                description=(description or "").strip() or None,
                experience_years=int(experience_years or 0),
            )
            db.session.add(doc)

        db.session.commit()
        return user

    @staticmethod
    def authenticate(*, username: str, password: str) -> User | None:
        user = db.session.execute(db.select(User).where(User.username == username)).scalar_one_or_none()
        if not user:
            return None
        if not user.check_password(password):
            return None
        return user

    @staticmethod
    def login(user: User) -> None:
        login_user(user)

    @staticmethod
    def logout() -> None:
        logout_user()

