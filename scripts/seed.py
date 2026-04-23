from datetime import date, time, timedelta
import os
import sys


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app import create_app
from app.extensions import db
from app.models.doctor import Doctor
from app.models.hospital import Hospital
from app.models.enums import UserRole
from app.models.schedule import Schedule
from app.models.user import User


def _get_or_create_user(username: str, password: str, role: UserRole) -> User:
    user = db.session.execute(db.select(User).where(User.username == username)).scalar_one_or_none()
    if user:
        return user
    user = User(username=username, role=role)
    user.set_password(password)
    db.session.add(user)
    db.session.flush()
    return user


def seed():
    admin = _get_or_create_user("admin", "admin123", UserRole.ADMIN)
    p1 = _get_or_create_user("patient1", "patient123", UserRole.PATIENT)
    p2 = _get_or_create_user("patient2", "patient123", UserRole.PATIENT)

    d1_user = _get_or_create_user("dr_anna", "doctor123", UserRole.DOCTOR)
    d2_user = _get_or_create_user("dr_binh", "doctor123", UserRole.DOCTOR)
    d3_user = _get_or_create_user("dr_chau", "doctor123", UserRole.DOCTOR)

    def get_or_create_doctor(user: User, specialty: str, exp: int, desc: str, hospital_name: str | None) -> Doctor:
        doc = db.session.execute(db.select(Doctor).where(Doctor.user_id == user.id)).scalar_one_or_none()
        if doc:
            if hospital_name and not doc.hospital_id:
                hospital = db.session.execute(db.select(Hospital).where(Hospital.name == hospital_name)).scalar_one_or_none()
                if not hospital:
                    hospital = Hospital(name=hospital_name)
                    db.session.add(hospital)
                    db.session.flush()
                doc.hospital_id = hospital.id
            return doc
        hospital_id = None
        if hospital_name:
            hospital = db.session.execute(db.select(Hospital).where(Hospital.name == hospital_name)).scalar_one_or_none()
            if not hospital:
                hospital = Hospital(name=hospital_name)
                db.session.add(hospital)
                db.session.flush()
            hospital_id = hospital.id
        doc = Doctor(
            user_id=user.id,
            specialty=specialty,
            experience_years=exp,
            description=desc,
            hospital_id=hospital_id,
        )
        db.session.add(doc)
        db.session.flush()
        return doc

    doc1 = get_or_create_doctor(d1_user, "Cardiology", 8, "Heart specialist with focus on preventive care.", "Hospital A")
    doc2 = get_or_create_doctor(d2_user, "Dermatology", 5, "Skin & allergy clinic, modern treatment methods.", "Clinic B")
    doc3 = get_or_create_doctor(d3_user, "Pediatrics", 10, "Child health and vaccination consultation.", "Hospital C")

    def add_slots(doc: Doctor, start_day_offset: int):
        base = date.today() + timedelta(days=start_day_offset)
        slots = [
            (base, time(9, 0), time(9, 30)),
            (base, time(9, 30), time(10, 0)),
            (base, time(10, 0), time(10, 30)),
            (base + timedelta(days=1), time(14, 0), time(14, 30)),
            (base + timedelta(days=1), time(14, 30), time(15, 0)),
        ]
        for d, st, et in slots:
            exists = db.session.execute(
                db.select(Schedule.id).where(
                    Schedule.doctor_id == doc.id,
                    Schedule.date == d,
                    Schedule.start_time == st,
                    Schedule.end_time == et,
                )
            ).scalar_one_or_none()
            if exists is None:
                db.session.add(Schedule(doctor_id=doc.id, date=d, start_time=st, end_time=et, is_available=True))

    add_slots(doc1, 1)
    add_slots(doc2, 2)
    add_slots(doc3, 3)

    db.session.commit()

    print("Seed completed.")
    print("Sample accounts:")
    print("- admin / admin123 (ADMIN)")
    print("- patient1 / patient123 (PATIENT)")
    print("- patient2 / patient123 (PATIENT)")
    print("- dr_anna / doctor123 (DOCTOR)")
    print("- dr_binh / doctor123 (DOCTOR)")
    print("- dr_chau / doctor123 (DOCTOR)")


def main():
    app = create_app()
    with app.app_context():
        seed()


if __name__ == "__main__":
    main()

