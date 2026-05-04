import unittest
from datetime import date, time
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import Config

from app import create_app
from app.extensions import db
from app.models.appointment import Appointment
from app.models.doctor import Doctor
from app.models.enums import AppointmentStatus, UserRole
from app.models.hospital import Hospital
from app.models.schedule import Schedule
from app.models.user import User
from app.models.weekly_shift import WeeklyShift
from app.services.schedule_service import ScheduleService


class TestWorkScheduleManagement(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._old_db_uri = Config.SQLALCHEMY_DATABASE_URI
        Config.SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
        cls.app = create_app()
        cls.app.config["TESTING"] = True
        cls.ctx = cls.app.app_context()
        cls.ctx.push()

    @classmethod
    def tearDownClass(cls):
        db.session.remove()
        db.engine.dispose()
        cls.ctx.pop()
        Config.SQLALCHEMY_DATABASE_URI = cls._old_db_uri

    def setUp(self):
        db.drop_all()
        db.create_all()

    def _create_doctor(self, username: str) -> Doctor:
        user = User(username=username, role=UserRole.DOCTOR, email=f"{username}@example.com", phone="0906666666")
        user.set_password("123456")
        db.session.add(user)
        db.session.flush()
        hospital = Hospital(name=f"Hospital_{username}")
        db.session.add(hospital)
        db.session.flush()
        doctor = Doctor(
            user_id=user.id,
            specialty="Noi khoa",
            hospital_id=hospital.id,
            experience_years=7,
        )
        db.session.add(doctor)
        db.session.commit()
        return doctor

    def test_case_1_generate_schedule_from_weekly_shift(self):
        doctor = self._create_doctor("doctor_weekly_a")
        week_start = date(2026, 5, 4)
        shift = WeeklyShift(
            doctor_id=doctor.id,
            week_start=week_start,
            weekday=2,
            start_time=time(8, 0),
            end_time=time(9, 0),
            is_active=True,
        )
        db.session.add(shift)
        db.session.commit()

        created = ScheduleService.ensure_week_schedules_from_templates(
            doctor_id=doctor.id, week_start=week_start
        )
        schedules = ScheduleService.list_doctor_schedules(doctor_id=doctor.id)

        self.assertEqual(1, created)
        self.assertEqual(1, len(schedules))
        self.assertEqual(date(2026, 5, 6), schedules[0].date)

    def test_case_2_delete_template_removes_unbooked_schedule(self):
        doctor = self._create_doctor("doctor_weekly_b")
        week_start = date(2026, 5, 4)
        shift = WeeklyShift(
            doctor_id=doctor.id,
            week_start=week_start,
            weekday=1,
            start_time=time(14, 0),
            end_time=time(15, 0),
            is_active=True,
        )
        slot = Schedule(
            doctor_id=doctor.id,
            date=date(2026, 5, 5),
            start_time=time(14, 0),
            end_time=time(15, 0),
            is_available=True,
        )
        db.session.add(shift)
        db.session.add(slot)
        db.session.commit()

        kept_booked, message = ScheduleService.delete_week_template_and_schedule(shift=shift)

        self.assertFalse(kept_booked)
        self.assertIsNone(message)
        self.assertIsNone(db.session.get(Schedule, slot.id))

    def test_case_3_delete_template_keeps_booked_schedule(self):
        patient = User(
            username="patient_weekly",
            role=UserRole.PATIENT,
            email="patient_weekly@example.com",
            phone="0904444444",
        )
        patient.set_password("123456")
        db.session.add(patient)
        db.session.flush()

        doctor = self._create_doctor("doctor_weekly_c")
        week_start = date(2026, 5, 4)
        shift = WeeklyShift(
            doctor_id=doctor.id,
            week_start=week_start,
            weekday=4,
            start_time=time(9, 0),
            end_time=time(10, 0),
            is_active=True,
        )
        slot = Schedule(
            doctor_id=doctor.id,
            date=date(2026, 5, 8),
            start_time=time(9, 0),
            end_time=time(10, 0),
            is_available=False,
        )
        db.session.add(shift)
        db.session.add(slot)
        db.session.flush()

        appointment = Appointment(
            patient_id=patient.id,
            doctor_id=doctor.id,
            schedule_id=slot.id,
            booking_for="self",
            contact_fullname="patient_weekly",
            contact_email=patient.email,
            contact_phone=patient.phone,
            symptoms="test",
            status=AppointmentStatus.CONFIRMED,
        )
        db.session.add(appointment)
        db.session.commit()

        kept_booked, message = ScheduleService.delete_week_template_and_schedule(shift=shift)

        self.assertTrue(kept_booked)
        self.assertTrue(bool(message))
        self.assertIsNotNone(db.session.get(Schedule, slot.id))


if __name__ == "__main__":
    unittest.main()