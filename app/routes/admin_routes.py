from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import login_required

from app.extensions import db
from app.models.doctor import Doctor
from app.models.disease import Disease
from app.models.hospital import Hospital
from app.models.enums import UserRole
from app.models.payment_transaction import PaymentTransaction
from app.models.schedule import Schedule
from app.models.user import User
from app.services.authz import roles_required
from app.services.chatbot_service import ChatbotService
from app.services.forms import DiseaseAdminForm, HospitalAdminForm

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.get("/dashboard")
@login_required
@roles_required(UserRole.ADMIN)
def dashboard():
    hospital_form = HospitalAdminForm()
    username = (request.args.get("username") or "").strip()
    doctor_name = (request.args.get("doctor_name") or "").strip()
    patient_name = (request.args.get("patient_name") or "").strip()
    role_value = (request.args.get("role") or "").strip().upper()
    hospital_name = (request.args.get("hospital_name") or "").strip()
    specialty = (request.args.get("specialty") or "").strip()

    stmt = db.select(User).outerjoin(Doctor, Doctor.user_id == User.id).outerjoin(Hospital, Hospital.id == Doctor.hospital_id)

    if username:
        stmt = stmt.where(User.username.ilike(f"%{username}%"))
    if doctor_name:
        stmt = stmt.where(User.role == UserRole.DOCTOR, User.username.ilike(f"%{doctor_name}%"))
    if patient_name:
        stmt = stmt.where(User.role == UserRole.PATIENT, User.username.ilike(f"%{patient_name}%"))
    if role_value in {UserRole.ADMIN.value, UserRole.DOCTOR.value, UserRole.PATIENT.value}:
        stmt = stmt.where(User.role == UserRole(role_value))
    if hospital_name:
        stmt = stmt.where(User.role == UserRole.DOCTOR, Hospital.name.ilike(f"%{hospital_name}%"))
    if specialty:
        stmt = stmt.where(User.role == UserRole.DOCTOR, Doctor.specialty.ilike(f"%{specialty}%"))

    users = list(db.session.execute(stmt.order_by(User.id.desc())).scalars().all())
    hospitals = list(db.session.execute(db.select(Hospital).order_by(Hospital.name.asc())).scalars().all())
    filters = {
        "username": username,
        "doctor_name": doctor_name,
        "patient_name": patient_name,
        "role": role_value,
        "hospital_name": hospital_name,
        "specialty": specialty,
    }
    return render_template(
        "admin/dashboard.html",
        users=users,
        filters=filters,
        hospital_form=hospital_form,
        hospitals=hospitals,
    )


@admin_bp.post("/hospitals/create")
@login_required
@roles_required(UserRole.ADMIN)
def create_hospital():
    form = HospitalAdminForm()
    if not form.validate_on_submit():
        flash("Hospital name is required (2-160 chars).", "danger")
        return redirect(url_for("admin.dashboard"))

    hospital_name = form.name.data.strip()
    existing = db.session.execute(db.select(Hospital.id).where(Hospital.name == hospital_name)).scalar_one_or_none()
    if existing is not None:
        flash("Hospital already exists.", "warning")
        return redirect(url_for("admin.dashboard"))

    try:
        db.session.add(Hospital(name=hospital_name))
        db.session.commit()
        flash("Hospital created successfully.", "success")
    except Exception:
        db.session.rollback()
        flash("Could not create hospital.", "danger")
    return redirect(url_for("admin.dashboard"))


@admin_bp.post("/users/<int:user_id>/delete")
@login_required
@roles_required(UserRole.ADMIN)
def delete_user(user_id: int):
    user = db.session.get(User, user_id)
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for("admin.dashboard"))
    if user.role == UserRole.ADMIN:
        flash("Cannot delete ADMIN account.", "danger")
        return redirect(url_for("admin.dashboard"))

    try:
        # Clean payment transactions by patient ownership.
        db.session.execute(db.delete(PaymentTransaction).where(PaymentTransaction.patient_id == user.id))

        # If deleting a doctor-account user, delete doctor profile first.
        # This avoids ORM trying to set doctors.user_id = NULL (NOT NULL column).
        doctor = db.session.execute(db.select(Doctor).where(Doctor.user_id == user.id)).scalar_one_or_none()
        if doctor:
            doctor_schedule_ids = db.session.execute(
                db.select(Schedule.id).where(Schedule.doctor_id == doctor.id)
            ).scalars().all()
            if doctor_schedule_ids:
                db.session.execute(
                    db.delete(PaymentTransaction).where(PaymentTransaction.schedule_id.in_(doctor_schedule_ids))
                )
            db.session.delete(doctor)

        db.session.delete(user)
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash("Delete failed. Data constraints prevented this action.", "danger")
        return redirect(url_for("admin.dashboard"))

    flash("User deleted successfully.", "success")
    return redirect(url_for("admin.dashboard"))


@admin_bp.get("/diseases")
@login_required
@roles_required(UserRole.ADMIN, UserRole.DOCTOR)
def diseases_list():
    q = (request.args.get("q") or "").strip()
    stmt = db.select(Disease).order_by(Disease.id.desc())
    if q:
        stmt = stmt.where(
            db.or_(
                Disease.name.ilike(f"%{q}%"),
                Disease.specialty.ilike(f"%{q}%"),
                Disease.symptoms.ilike(f"%{q}%"),
            )
        )
    diseases = list(db.session.execute(stmt).scalars().all())
    return render_template("admin/diseases.html", diseases=diseases, q=q)


@admin_bp.get("/diseases/new")
@admin_bp.post("/diseases/new")
@login_required
@roles_required(UserRole.ADMIN, UserRole.DOCTOR)
def disease_new():
    form = DiseaseAdminForm()
    if form.validate_on_submit():
        try:
            disease = Disease(
                name=form.name.data.strip(),
                symptoms=form.symptoms.data.strip(),
                description=form.description.data.strip(),
                specialty=form.specialty.data.strip(),
            )
            db.session.add(disease)
            db.session.flush()
            disease_id = int(disease.id)
            db.session.commit()
            if not disease_id:
                flash("Disease saved but could not read new ID for embedding.", "warning")
            else:
                try:
                    ChatbotService.persist_embedding_for_disease(disease_id)
                    db.session.commit()
                    flash("Disease created and embedding saved.", "success")
                except Exception:
                    db.session.rollback()
                    flash(
                        "Disease created. Embedding update failed — please retry editing this disease.",
                        "warning",
                    )
            return redirect(url_for("admin.diseases_list"))
        except Exception:
            db.session.rollback()
            flash("Could not save disease. Ensure table `diseases` exists (run migration).", "danger")
    return render_template("admin/disease_form.html", form=form)


@admin_bp.get("/diseases/<int:disease_id>/edit")
@admin_bp.post("/diseases/<int:disease_id>/edit")
@login_required
@roles_required(UserRole.ADMIN)
def disease_edit(disease_id: int):
    disease = db.session.get(Disease, disease_id)
    if not disease:
        flash("Disease not found.", "danger")
        return redirect(url_for("admin.diseases_list"))

    form = DiseaseAdminForm(obj=disease)
    if form.validate_on_submit():
        disease.name = form.name.data.strip()
        disease.symptoms = form.symptoms.data.strip()
        disease.description = form.description.data.strip()
        disease.specialty = form.specialty.data.strip()
        try:
            db.session.commit()
            try:
                ChatbotService.persist_embedding_for_disease(disease.id)
                db.session.commit()
                flash("Disease updated and embedding refreshed.", "success")
            except Exception:
                db.session.rollback()
                flash("Disease updated. Embedding refresh failed.", "warning")
        except Exception:
            db.session.rollback()
            flash("Could not update disease.", "danger")
            return render_template("admin/disease_form.html", form=form, mode="edit")
        return redirect(url_for("admin.diseases_list"))

    return render_template("admin/disease_form.html", form=form, mode="edit")


@admin_bp.post("/diseases/<int:disease_id>/delete")
@login_required
@roles_required(UserRole.ADMIN)
def disease_delete(disease_id: int):
    try:
        disease = db.session.get(Disease, disease_id)
        if not disease:
            flash("Disease not found.", "danger")
            return redirect(url_for("admin.diseases_list"))
        db.session.delete(disease)
        db.session.commit()
        flash("Disease deleted.", "info")
    except Exception:
        db.session.rollback()
        flash("Delete failed.", "danger")
    return redirect(url_for("admin.diseases_list"))

