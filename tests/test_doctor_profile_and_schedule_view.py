import unittest
from datetime import date, time
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import Config

from app import create_app
from app.extensions import db
from app.models.doctor import Doctor
from app.models.enums import UserRole
from app.models.hospital import Hospital
from app.models.schedule import Schedule
from app.models.user import User
from app.services.doctor_service import DoctorService


class TestDoctorProfileAndScheduleView(unittest.TestCase):
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

    def _create_doctor_with_schedule(self, username: str) -> Doctor:
        user = User(username=username, role=UserRole.DOCTOR, email=f"{username}@example.com", phone="0905555555")
        user.set_password("123456")
        db.session.add(user)
        db.session.flush()

        hospital = Hospital(name="Benh vien Ho So")
        db.session.add(hospital)
        db.session.flush()

        doctor = Doctor(
            user_id=user.id,
            specialty="Tai mui hong",
            hospital_id=hospital.id,
            description="Mo ta bac si",
            experience_years=6,
        )
        db.session.add(doctor)
        db.session.flush()

        schedule = Schedule(
            doctor_id=doctor.id,
            date=date(2030, 1, 10),
            start_time=time(9, 0),
            end_time=time(10, 0),
            is_available=True,
        )
        db.session.add(schedule)
        db.session.commit()
        return doctor

    def test_case_1_get_doctor_profile_success(self):
        doctor = self._create_doctor_with_schedule("doctor_profile_1")
        loaded_doctor = DoctorService.get_doctor(doctor.id)

        self.assertIsNotNone(loaded_doctor)
        self.assertEqual("doctor_profile_1", loaded_doctor.user.username)
        self.assertEqual("Tai mui hong", loaded_doctor.specialty)

    def test_case_2_get_available_schedules_success(self):
        doctor = self._create_doctor_with_schedule("doctor_profile_2")
        schedules = DoctorService.get_available_schedules(
            doctor_id=doctor.id,
            from_date=date(2030, 1, 1),
        )

        self.assertEqual(1, len(schedules))
        self.assertEqual(date(2030, 1, 10), schedules[0].date)
        self.assertTrue(schedules[0].is_available)


if __name__ == "__main__":
    unittest.main()
