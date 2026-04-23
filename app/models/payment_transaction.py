from datetime import datetime

from app.extensions import db

from .enums import PaymentStatus


class PaymentTransaction(db.Model):
    __tablename__ = "payment_transactions"

    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    schedule_id = db.Column(db.Integer, db.ForeignKey("schedules.id"), nullable=False, index=True)
    booking_for = db.Column(db.String(20), nullable=False, default="self")
    contact_fullname = db.Column(db.String(80), nullable=False)
    contact_email = db.Column(db.String(255), nullable=True)
    contact_phone = db.Column(db.String(20), nullable=False)
    symptoms = db.Column(db.Text, nullable=True)

    vnp_txn_ref = db.Column(db.String(64), nullable=False, unique=True, index=True)
    amount_vnd = db.Column(db.Integer, nullable=False)  # amount in VND (major unit)
    status = db.Column(db.Enum(PaymentStatus), nullable=False, default=PaymentStatus.PENDING, index=True)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

