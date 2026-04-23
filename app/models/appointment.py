from datetime import datetime

from app.extensions import db

from .enums import AppointmentStatus


class Appointment(db.Model):
    __tablename__ = "appointments"

    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    doctor_id = db.Column(db.Integer, db.ForeignKey("doctors.id"), nullable=False, index=True)
    schedule_id = db.Column(db.Integer, db.ForeignKey("schedules.id"), nullable=False, unique=True)
    booking_for = db.Column(db.String(20), nullable=False, default="self", index=True)
    contact_fullname = db.Column(db.String(80), nullable=False)
    contact_email = db.Column(db.String(255), nullable=True)
    contact_phone = db.Column(db.String(20), nullable=False, index=True)
    symptoms = db.Column(db.Text, nullable=True)

    status = db.Column(db.Enum(AppointmentStatus), nullable=False, default=AppointmentStatus.PENDING, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    patient = db.relationship("User", back_populates="patient_appointments", foreign_keys=[patient_id])
    doctor = db.relationship("Doctor", back_populates="appointments", foreign_keys=[doctor_id])
    schedule = db.relationship("Schedule", back_populates="appointment", foreign_keys=[schedule_id])
    review = db.relationship("DoctorReview", back_populates="appointment", uselist=False, cascade="all, delete-orphan")

