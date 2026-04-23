from datetime import date, timedelta

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.models.appointment import Appointment
from app.models.doctor import Doctor
from app.models.hospital import Hospital
from app.models.enums import AppointmentStatus, UserRole
from app.models.schedule import Schedule
from app.models.weekly_shift import WeeklyShift
from app.services.appointment_service import AppointmentService
from app.services.authz import roles_required
from app.services.forms import DoctorProfileForm, ScheduleForm, UpdateAppointmentStatusForm, WeeklyShiftForm
from app.services.schedule_service import ScheduleService

doctor_bp = Blueprint("doctor", __name__, url_prefix="/doctor")


def _is_admin() -> bool:
    return current_user.role == UserRole.ADMIN


def _redirect_with_doctor_context(endpoint: str, doctor_id: int):
    if _is_admin():
        return redirect(url_for(endpoint, doctor_id=doctor_id))
    return redirect(url_for(endpoint))


def _require_doctor_profile():
    if current_user.doctor_profile:
        return current_user.doctor_profile
    if current_user.role == UserRole.ADMIN:
        doctor_id = request.args.get("doctor_id", type=int)
        if doctor_id:
            doctor = db.session.get(Doctor, doctor_id)
            if doctor:
                return doctor
        doctor = db.session.execute(db.select(Doctor).order_by(Doctor.id.asc())).scalars().first()
        if doctor:
            return doctor
    abort(403)


@doctor_bp.get("/dashboard")
@login_required
@roles_required(UserRole.DOCTOR)
def dashboard():
    doctor = _require_doctor_profile()
    schedules = ScheduleService.list_doctor_schedules(doctor_id=doctor.id)[:10]
    appts = AppointmentService.list_for_doctor(doctor_id=doctor.id)[:10]
    return render_template("doctor/dashboard.html", schedules=schedules, appointments=appts)


@doctor_bp.get("/profile")
@doctor_bp.post("/profile")
@login_required
@roles_required(UserRole.DOCTOR)
def profile():
    doctor = _require_doctor_profile()
    form = DoctorProfileForm(obj=doctor)
    if request.method == "GET":
        form.hospital_name.data = doctor.hospital.name if doctor.hospital else ""

    if form.validate_on_submit():
        doctor.specialty = form.specialty.data.strip()
        doctor.experience_years = int(form.experience_years.data)
        doctor.description = (form.description.data or "").strip() or None

        hospital_name = (form.hospital_name.data or "").strip()
        if hospital_name:
            hospital = db.session.execute(
                db.select(Hospital).where(Hospital.name == hospital_name)
            ).scalar_one_or_none()
            if not hospital:
                hospital = Hospital(name=hospital_name)
                db.session.add(hospital)
                db.session.flush()
            doctor.hospital_id = hospital.id
        else:
            doctor.hospital_id = None

        db.session.commit()
        flash("Profile updated", "success")
        return _redirect_with_doctor_context("doctor.profile", doctor.id)

    return render_template("doctor/profile.html", doctor=doctor, form=form)

