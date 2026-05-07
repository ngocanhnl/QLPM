import unittest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import Config

from app import create_app
from app.extensions import db
from app.models.doctor import Doctor
from app.models.enums import UserRole
from app.models.hospital import Hospital
from app.models.user import User
from app.services.doctor_service import DoctorService


class TestDoctorSearch(unittest.TestCase):
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

    def _create_doctor(self, username: str, specialty: str, hospital_name: str) -> Doctor:
        user = User(username=username, role=UserRole.DOCTOR, email=f"{username}@example.com", phone="0900000000")
        user.set_password("123456")
        db.session.add(user)
        db.session.flush()

        hospital = db.session.execute(db.select(Hospital).where(Hospital.name == hospital_name)).scalar_one_or_none()
        if hospital is None:
            hospital = Hospital(name=hospital_name)
            db.session.add(hospital)
            db.session.flush()

        doctor = Doctor(user_id=user.id, specialty=specialty, hospital_id=hospital.id, experience_years=5)
        db.session.add(doctor)
        db.session.commit()
        return doctor

    def test_search_by_name_returns_matching_doctors(self):
        self._create_doctor("alpha_doctor", "Tim mach", "Benh vien A")
        self._create_doctor("alpha_second", "Than kinh", "Benh vien B")
        self._create_doctor("other_doctor", "Tim mach", "Benh vien C")

        results = DoctorService.search_doctors(doctor_name="alpha")
        self.assertEqual(2, len(results))

    def test_search_with_result_filters_by_hospital_and_specialty(self):
        doctor_a = self._create_doctor("alpha_one", "Tim mach", "Benh vien A")
        self._create_doctor("alpha_two", "Than kinh", "Benh vien B")

        results = DoctorService.search_doctors(
            doctor_name="alpha",
            exact_hospital_name="Benh vien A",
            exact_specialty="Tim mach",
        )
        self.assertEqual(1, len(results))
        self.assertEqual(doctor_a.id, results[0].id)


if __name__ == "__main__":
    unittest.main()
