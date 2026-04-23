from app.extensions import db


class Disease(db.Model):
    __tablename__ = "diseases"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False, index=True)
    symptoms = db.Column(db.Text, nullable=False)
    description = db.Column(db.Text, nullable=False)
    specialty = db.Column(db.String(120), nullable=False, index=True)
    # MySQL stores JSON text; PostgreSQL can store vector via migration/raw SQL.
    embedding = db.Column(db.Text, nullable=True)

