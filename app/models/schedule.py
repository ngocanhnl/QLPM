from app.extensions import db


class Schedule(db.Model):
    __tablename__ = "schedules"

    id = db.Column(db.Integer, primary_key=True)
    doctor_id = db.Column(db.Integer, db.ForeignKey("doctors.id"), nullable=False, index=True)

    date = db.Column(db.Date, nullable=False, index=True)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    is_available = db.Column(db.Boolean, nullable=False, default=True, index=True)

    doctor = db.relationship("Doctor", back_populates="schedules")
    appointment = db.relationship("Appointment", back_populates="schedule", uselist=False)

    __table_args__ = (
        db.UniqueConstraint("doctor_id", "date", "start_time", "end_time", name="uq_doctor_slot"),
    )

