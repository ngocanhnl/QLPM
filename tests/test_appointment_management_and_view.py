import unittest
from datetime import date, datetime, time, timedelta
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import Config

from app import create_app
from app.extensions import db
from app.models.doctor import Doctor
from app.models.enums import AppointmentStatus, UserRole
from app.models.hospital import Hospital
from app.models.schedule import Schedule
from app.models.user import User
from app.services.appointment_service import AppointmentService


class TestAppointmentManagementAndView(unittest.TestCase):
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

    def _create_user(self, username: str, role: UserRole, phone: str) -> User:
        user = User(username=username, role=role, email=f"{username}@example.com", phone=phone)
        user.set_password("123456")
        db.session.add(user)
        db.session.flush()
        return user

    def _create_doctor(self, username: str, hospital_name: str) -> Doctor:
        doctor_user = self._create_user(username, UserRole.DOCTOR, "0900999999")
        hospital = db.session.execute(db.select(Hospital).where(Hospital.name == hospital_name)).scalar_one_or_none()
        if not hospital:
            hospital = Hospital(name=hospital_name)
            db.session.add(hospital)
            db.session.flush()
        doctor = Doctor(
            user_id=doctor_user.id,
            specialty="Noi khoa",
            hospital_id=hospital.id,
            experience_years=5,
        )
        db.session.add(doctor)
        db.session.flush()
        return doctor

    def _create_slot(self, doctor: Doctor, slot_date: date, start: time, end: time, is_available: bool = True) -> Schedule:
        slot = Schedule(
            doctor_id=doctor.id,
            date=slot_date,
            start_time=start,
            end_time=end,
            is_available=is_available,
        )
        db.session.add(slot)
        db.session.commit()
        return slot

    def test_case_1_list_for_patient_includes_own_and_by_phone(self):
        patient_a = self._create_user("patient_a_mgmt", UserRole.PATIENT, "0901111111")
        patient_b = self._create_user("patient_b_mgmt", UserRole.PATIENT, "0902222222")
        doctor = self._create_doctor("doctor_mgmt_a", "Benh vien A")

        slot_1 = self._create_slot(doctor, date(2026, 5, 13), time(9, 0), time(10, 0), True)
        slot_2 = self._create_slot(doctor, date(2026, 5, 14), time(9, 0), time(10, 0), True)

        own_appt = AppointmentService.book(
            patient_id=patient_a.id,
            schedule_id=slot_1.id,
            booking_for="self",
            contact_fullname="patient_a_mgmt",
            contact_email=patient_a.email,
            contact_phone=patient_a.phone,
            symptoms="test",
        )

        # Patient B books for a relative whose phone matches patient A -> should appear in patient A's list.
        relative_appt = AppointmentService.book(
            patient_id=patient_b.id,
            schedule_id=slot_2.id,
            booking_for="relative",
            contact_fullname="relative_of_a",
            contact_email="relative_of_a@example.com",
            contact_phone=patient_a.phone,
            symptoms="test",
        )

        listed = AppointmentService.list_for_patient(patient_id=patient_a.id)
        listed_ids = {a.id for a in listed}
        self.assertIn(own_appt.id, listed_ids)
        self.assertIn(relative_appt.id, listed_ids)

    def test_case_2_list_for_patient_orders_by_created_at_desc(self):
        patient = self._create_user("patient_order", UserRole.PATIENT, "0903333333")
        doctor = self._create_doctor("doctor_order", "Benh vien Order")

        slot_1 = self._create_slot(doctor, date(2026, 5, 15), time(8, 0), time(9, 0), True)
        slot_2 = self._create_slot(doctor, date(2026, 5, 16), time(8, 0), time(9, 0), True)

        appt_older = AppointmentService.book(
            patient_id=patient.id,
            schedule_id=slot_1.id,
            booking_for="self",
            contact_fullname="patient_order",
            contact_email=patient.email,
            contact_phone=patient.phone,
            symptoms="older",
        )
        appt_newer = AppointmentService.book(
            patient_id=patient.id,
            schedule_id=slot_2.id,
            booking_for="self",
            contact_fullname="patient_order",
            contact_email=patient.email,
            contact_phone=patient.phone,
            symptoms="newer",
        )

        appt_older.created_at = datetime.utcnow() - timedelta(days=2)
        appt_newer.created_at = datetime.utcnow() - timedelta(days=1)
        db.session.commit()

        listed = AppointmentService.list_for_patient(patient_id=patient.id)
        self.assertGreaterEqual(len(listed), 2)
        self.assertEqual(appt_newer.id, listed[0].id)
        self.assertEqual(appt_older.id, listed[1].id)

    def test_case_3_list_for_doctor_filters_by_doctor(self):
        patient = self._create_user("patient_doc_filter", UserRole.PATIENT, "0904444444")
        doctor_a = self._create_doctor("doctor_filter_a", "Benh vien Filter")
        doctor_b = self._create_doctor("doctor_filter_b", "Benh vien Filter")

        slot_a = self._create_slot(doctor_a, date(2026, 5, 17), time(10, 0), time(11, 0), True)
        slot_b = self._create_slot(doctor_b, date(2026, 5, 18), time(10, 0), time(11, 0), True)

        appt_a = AppointmentService.book(
            patient_id=patient.id,
            schedule_id=slot_a.id,
            booking_for="self",
            contact_fullname="patient_doc_filter",
            contact_email=patient.email,
            contact_phone=patient.phone,
            symptoms="a",
        )
        AppointmentService.book(
            patient_id=patient.id,
            schedule_id=slot_b.id,
            booking_for="self",
            contact_fullname="patient_doc_filter",
            contact_email=patient.email,
            contact_phone=patient.phone,
            symptoms="b",
        )

        listed = AppointmentService.list_for_doctor(doctor_id=doctor_a.id)
        self.assertEqual(1, len(listed))
        self.assertEqual(appt_a.id, listed[0].id)

    def test_case_4_update_status_cancelled_frees_schedule(self):
        patient = self._create_user("patient_cancel", UserRole.PATIENT, "0905555555")
        doctor = self._create_doctor("doctor_cancel", "Benh vien Cancel")
        slot = self._create_slot(doctor, date(2026, 5, 19), time(9, 0), time(10, 0), True)

        appt = AppointmentService.book(
            patient_id=patient.id,
            schedule_id=slot.id,
            booking_for="self",
            contact_fullname="patient_cancel",
            contact_email=patient.email,
            contact_phone=patient.phone,
            symptoms="cancel",
        )

        self.assertFalse(slot.is_available)
        updated = AppointmentService.update_status(appointment=appt, status=AppointmentStatus.CANCELLED)
        self.assertEqual(AppointmentStatus.CANCELLED, updated.status)
        self.assertTrue(updated.schedule.is_available)

    def test_case_5_update_status_confirmed_keeps_schedule_unavailable(self):
        patient = self._create_user("patient_confirm", UserRole.PATIENT, "0906666666")
        doctor = self._create_doctor("doctor_confirm", "Benh vien Confirm")
        slot = self._create_slot(doctor, date(2026, 5, 20), time(9, 0), time(10, 0), True)

        appt = AppointmentService.book(
            patient_id=patient.id,
            schedule_id=slot.id,
            booking_for="self",
            contact_fullname="patient_confirm",
            contact_email=patient.email,
            contact_phone=patient.phone,
            symptoms="confirm",
        )

        self.assertFalse(slot.is_available)
        updated = AppointmentService.update_status(appointment=appt, status=AppointmentStatus.CONFIRMED)
        self.assertEqual(AppointmentStatus.CONFIRMED, updated.status)
        self.assertFalse(updated.schedule.is_available)


if __name__ == "__main__":
    unittest.main()

