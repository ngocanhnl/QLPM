from app.extensions import db


class Hospital(db.Model):
    __tablename__ = "hospitals"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False, unique=True, index=True)

    doctors = db.relationship("Doctor", back_populates="hospital")

