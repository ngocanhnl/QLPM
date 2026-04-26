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

@doctor_bp.get("/weekly")
@doctor_bp.post("/weekly")
@login_required
@roles_required(UserRole.DOCTOR)
def weekly():
    doctor = _require_doctor_profile()
    form = WeeklyShiftForm()

    if form.validate_on_submit():
        shift = WeeklyShift(
            doctor_id=doctor.id,
            weekday=int(form.weekday.data),
            start_time=form.start_time.data,
            end_time=form.end_time.data,
            is_active=True,
        )
        db.session.add(shift)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            flash("Shift already exists or invalid", "danger")
        else:
            flash("Weekly shift added", "success")
        return _redirect_with_doctor_context("doctor.weekly", doctor.id)

    created = ScheduleService.ensure_next_days_from_weekly_shifts(doctor_id=doctor.id, days_ahead=7)
    if created:
        flash(f"Generated {created} slots for next 7 days", "info")

    shifts = list(
        db.session.execute(
            db.select(WeeklyShift)
            .where(WeeklyShift.doctor_id == doctor.id)
            .order_by(WeeklyShift.weekday, WeeklyShift.start_time)
        ).scalars().all()
    )

    start = date.today()
    days = [start + timedelta(days=i) for i in range(7)]
    schedules = ScheduleService.list_doctor_schedules(doctor_id=doctor.id)
    schedules_by_date: dict[date, list[Schedule]] = {d: [] for d in days}
    for s in schedules:
        if s.date in schedules_by_date:
            schedules_by_date[s.date].append(s)
    for d in days:
        schedules_by_date[d].sort(key=lambda x: x.start_time)

    weekday_labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    return render_template(
        "doctor/weekly.html",
        form=form,
        shifts=shifts,
        days=days,
        schedules_by_date=schedules_by_date,
        weekday_labels=weekday_labels,
    )


@doctor_bp.post("/weekly/<int:shift_id>/delete")
@login_required
@roles_required(UserRole.DOCTOR)
def weekly_delete(shift_id: int):
    doctor = _require_doctor_profile()
    shift = db.session.get(WeeklyShift, shift_id)
    if not shift:
        abort(404)
    if not _is_admin() and shift.doctor_id != doctor.id:
        abort(404)
    db.session.delete(shift)
    db.session.commit()
    flash("Weekly shift deleted", "info")
    return _redirect_with_doctor_context("doctor.weekly", shift.doctor_id)


@doctor_bp.get("/schedules")
@login_required
@roles_required(UserRole.DOCTOR)
def schedules():
    doctor = _require_doctor_profile()
    schedules = ScheduleService.list_doctor_schedules(doctor_id=doctor.id)
    return render_template("doctor/schedules.html", schedules=schedules)


@doctor_bp.get("/schedules/new")
@doctor_bp.post("/schedules/new")
@login_required
@roles_required(UserRole.DOCTOR)
def schedule_create():
    doctor = _require_doctor_profile()
    form = ScheduleForm()
    if form.validate_on_submit():
        try:
            ScheduleService.create_schedule(
                doctor_id=doctor.id,
                date_value=form.date.data,
                start_time_value=form.start_time.data,
                end_time_value=form.end_time.data,
                is_available=(form.is_available.data == "1"),
            )
        except ValueError as e:
            flash(str(e), "danger")
            return render_template("doctor/schedule_form.html", form=form, mode="create")

        flash("Schedule created", "success")
        return _redirect_with_doctor_context("doctor.schedules", doctor.id)

    return render_template("doctor/schedule_form.html", form=form, mode="create")


@doctor_bp.get("/schedules/<int:schedule_id>/edit")
@doctor_bp.post("/schedules/<int:schedule_id>/edit")
@login_required
@roles_required(UserRole.DOCTOR)
def schedule_edit(schedule_id: int):
    doctor = _require_doctor_profile()
    schedule = db.session.get(Schedule, schedule_id)
    if not schedule:
        abort(404)
    if not _is_admin() and schedule.doctor_id != doctor.id:
        abort(404)
    form = ScheduleForm(obj=schedule)
    form.is_available.data = "1" if schedule.is_available else "0"
    if form.validate_on_submit():
        try:
            ScheduleService.update_schedule(
                schedule=schedule,
                date_value=form.date.data,
                start_time_value=form.start_time.data,
                end_time_value=form.end_time.data,
                is_available=(form.is_available.data == "1"),
            )
        except ValueError as e:
            flash(str(e), "danger")
            return render_template("doctor/schedule_form.html", form=form, mode="edit")

        flash("Schedule updated", "success")
        return _redirect_with_doctor_context("doctor.schedules", schedule.doctor_id)

    return render_template("doctor/schedule_form.html", form=form, mode="edit")


@doctor_bp.post("/schedules/<int:schedule_id>/delete")
@login_required
@roles_required(UserRole.DOCTOR)
def schedule_delete(schedule_id: int):
    doctor = _require_doctor_profile()
    schedule = db.session.get(Schedule, schedule_id)
    if not schedule:
        abort(404)
    if not _is_admin() and schedule.doctor_id != doctor.id:
        abort(404)
    try:
        ScheduleService.delete_schedule(schedule)
    except ValueError as e:
        flash(str(e), "danger")
        return _redirect_with_doctor_context("doctor.schedules", schedule.doctor_id)
    flash("Schedule deleted", "success")
    return _redirect_with_doctor_context("doctor.schedules", schedule.doctor_id)


@doctor_bp.get("/appointments")
@login_required
@roles_required(UserRole.DOCTOR)
def appointments():
    doctor = _require_doctor_profile()
    appts = AppointmentService.list_for_doctor(doctor_id=doctor.id)
    return render_template("doctor/appointments.html", appointments=appts)


@doctor_bp.get("/appointments/<int:appointment_id>")
@doctor_bp.post("/appointments/<int:appointment_id>")
@login_required
@roles_required(UserRole.DOCTOR)
def appointment_detail(appointment_id: int):
    doctor = _require_doctor_profile()
    appt = db.session.get(Appointment, appointment_id)
    if not appt:
        abort(404)
    if not _is_admin() and appt.doctor_id != doctor.id:
        abort(404)
    form = UpdateAppointmentStatusForm()
    if form.validate_on_submit():
        AppointmentService.update_status(appointment=appt, status=AppointmentStatus(form.status.data))
        flash("Appointment updated", "success")
        return _redirect_with_doctor_context("doctor.appointments", appt.doctor_id)
    return render_template("doctor/appointment_detail.html", appointment=appt, form=form)

