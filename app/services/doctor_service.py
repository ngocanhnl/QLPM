from datetime import date

from app.extensions import db
from app.models.doctor import Doctor
from app.models.hospital import Hospital
from app.models.schedule import Schedule
from app.models.user import User


class DoctorService:
    @staticmethod
    def list_specialties() -> list[str]:
        rows = db.session.execute(db.select(Doctor.specialty).distinct().order_by(Doctor.specialty)).all()
        return [r[0] for r in rows]

    @staticmethod
    def list_hospitals() -> list[str]:
        rows = db.session.execute(db.select(Hospital.name).distinct().order_by(Hospital.name)).all()
        return [r[0] for r in rows]

    @staticmethod
    def list_doctor_names() -> list[str]:
        rows = (
            db.session.execute(
                db.select(User.username).join(Doctor).distinct().order_by(User.username)
            ).all()
        )
        return [r[0] for r in rows]

    @staticmethod
    def search_doctors(
        *,
        doctor_name: str | None = None,
        hospital_name: str | None = None,
        specialty: str | None,
        min_experience_years: int | None = None,
        max_experience_years: int | None = None,
    ) -> list[Doctor]:
        stmt = db.select(Doctor).join(User).outerjoin(Hospital).order_by(User.username)
        if doctor_name:
            stmt = stmt.where(User.username.ilike(f"%{doctor_name.strip()}%"))
        if hospital_name:
            stmt = stmt.where(Hospital.name.ilike(f"%{hospital_name.strip()}%"))
        if specialty:
            stmt = stmt.where(Doctor.specialty.ilike(f"%{specialty.strip()}%"))
        if min_experience_years is not None:
            stmt = stmt.where(Doctor.experience_years >= int(min_experience_years))
        if max_experience_years is not None:
            stmt = stmt.where(Doctor.experience_years <= int(max_experience_years))
        return list(db.session.execute(stmt).scalars().all())

    @staticmethod
    def get_doctor(doctor_id: int) -> Doctor | None:
        return db.session.get(Doctor, doctor_id)

    @staticmethod
    def get_available_schedules(*, doctor_id: int, from_date: date | None = None) -> list[Schedule]:
        stmt = (
            db.select(Schedule)
            .where(Schedule.doctor_id == doctor_id, Schedule.is_available.is_(True))
            .order_by(Schedule.date, Schedule.start_time)
        )
        if from_date:
            stmt = stmt.where(Schedule.date >= from_date)
        return list(db.session.execute(stmt).scalars().all())

    @staticmethod
    def list_hospital_options() -> list[tuple[int, str]]:
        rows = db.session.execute(db.select(Hospital.id, Hospital.name).order_by(Hospital.name.asc())).all()
        return [(int(h_id), h_name) for h_id, h_name in rows]

    @staticmethod
    def list_doctor_options(*, hospital_id: int | None = None) -> list[tuple[int, str]]:
        stmt = db.select(Doctor.id, User.username).join(User, User.id == Doctor.user_id).order_by(User.username.asc())
        if hospital_id:
            stmt = stmt.where(Doctor.hospital_id == hospital_id)
        rows = db.session.execute(stmt).all()
        return [(int(d_id), username) for d_id, username in rows]

