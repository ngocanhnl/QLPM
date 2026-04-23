from datetime import datetime

from app.extensions import db


class DoctorReview(db.Model):
    __tablename__ = "doctor_reviews"

    id = db.Column(db.Integer, primary_key=True)

    # Each appointment can be rated only once.
    appointment_id = db.Column(
        db.Integer,
        db.ForeignKey("appointments.id"),
        nullable=False,
        unique=True,
        index=True,
    )

    doctor_id = db.Column(db.Integer, db.ForeignKey("doctors.id"), nullable=False, index=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)

    stars = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    appointment = db.relationship("Appointment", back_populates="review", foreign_keys=[appointment_id], uselist=False)
    doctor = db.relationship("Doctor", back_populates="reviews", foreign_keys=[doctor_id])
    patient = db.relationship("User", foreign_keys=[patient_id])

