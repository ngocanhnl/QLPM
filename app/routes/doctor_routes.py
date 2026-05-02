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


def _start_of_week(value: date) -> date:
    return value - timedelta(days=value.weekday())


def _parse_iso_date(raw_value: str | None, fallback: date) -> date:
    if not raw_value:
        return fallback
    try:
        return date.fromisoformat(raw_value)
    except ValueError:
        return fallback


def _week_options(center_week_start: date, past_weeks: int = 2, future_weeks: int = 10) -> list[tuple[str, str]]:
    options: list[tuple[str, str]] = []
    for offset in range(-past_weeks, future_weeks + 1):
        start = center_week_start + timedelta(days=offset * 7)
        end = start + timedelta(days=6)
        label = f"Tuan {start.strftime('%d/%m/%Y')} - {end.strftime('%d/%m/%Y')}"
        options.append((start.isoformat(), label))
    return options


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
        if _is_admin():
            doctor.price_vnd = int(form.price_vnd.data)

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
    today = date.today()
    raw_week_start = request.form.get("week_start") if request.method == "POST" else request.args.get("week_start", type=str)
    requested_anchor = _parse_iso_date(raw_week_start, today)
    week_start = _start_of_week(requested_anchor)
    week_end = week_start + timedelta(days=6)
    selected_date = _parse_iso_date(request.args.get("selected_date", type=str), today)
    if not (week_start <= selected_date <= week_end):
        selected_date = week_start
    week_options = _week_options(week_start)
    selected_apply_weeks = [week_start.isoformat()]

    if request.method == "POST":
        selected_date = _parse_iso_date(request.form.get("selected_date"), selected_date)
        if not (week_start <= selected_date <= week_end):
            selected_date = week_start
        form.weekday.data = str(selected_date.weekday())
        selected_apply_weeks = request.form.getlist("apply_weeks") or [week_start.isoformat()]

    if form.validate_on_submit():
        apply_weeks = sorted({_parse_iso_date(raw_value, week_start).isoformat() for raw_value in selected_apply_weeks})
        if not apply_weeks:
            flash("Vui long chon it nhat mot tuan ap dung.", "danger")
        else:
            weekday = selected_date.weekday()
            target_weeks = [date.fromisoformat(value) for value in apply_weeks]
            existing_week_rows = db.session.execute(
                db.select(WeeklyShift.week_start).where(
                    WeeklyShift.doctor_id == doctor.id,
                    WeeklyShift.week_start.in_(target_weeks),
                    WeeklyShift.weekday == weekday,
                    WeeklyShift.start_time == form.start_time.data,
                    WeeklyShift.end_time == form.end_time.data,
                )
            ).scalars().all()
            existing_week_set = set(existing_week_rows)

            created_templates = 0
            for target_week in target_weeks:
                if target_week in existing_week_set:
                    continue
                db.session.add(
                    WeeklyShift(
                        doctor_id=doctor.id,
                        week_start=target_week,
                        weekday=weekday,
                        start_time=form.start_time.data,
                        end_time=form.end_time.data,
                        is_active=True,
                    )
                )
                created_templates += 1

            if created_templates:
                db.session.commit()
            generated_slots = 0
            for target_week in target_weeks:
                generated_slots += ScheduleService.ensure_week_schedules_from_templates(
                    doctor_id=doctor.id,
                    week_start=target_week,
                )

            skipped_templates = len(target_weeks) - created_templates
            if created_templates:
                flash(f"Da tao {created_templates} ca mau cho cac tuan da chon.", "success")
            if generated_slots:
                flash(f"Da sinh {generated_slots} slot tu dong tu cac ca mau vua chon.", "info")
            if skipped_templates:
                flash(f"Bo qua {skipped_templates} tuan vi da co ca mau trung khung gio.", "warning")
        redirect_params = {"week_start": week_start.isoformat(), "selected_date": selected_date.isoformat()}
        if _is_admin():
            redirect_params["doctor_id"] = doctor.id
        return redirect(url_for("doctor.weekly", **redirect_params))

    created = ScheduleService.ensure_week_schedules_from_templates(doctor_id=doctor.id, week_start=week_start)
    if created:
        flash(f"Generated {created} slots for the selected week", "info")

    shifts = list(
        db.session.execute(
            db.select(WeeklyShift)
            .where(WeeklyShift.doctor_id == doctor.id, WeeklyShift.week_start == week_start)
            .order_by(WeeklyShift.weekday, WeeklyShift.start_time)
        ).scalars().all()
    )

    days = [week_start + timedelta(days=i) for i in range(7)]
    schedules = [
        s
        for s in ScheduleService.list_doctor_schedules(doctor_id=doctor.id)
        if week_start <= s.date <= week_end
    ]
    schedules_by_date: dict[date, list[Schedule]] = {d: [] for d in days}
    for s in schedules:
        if s.date in schedules_by_date:
            schedules_by_date[s.date].append(s)
    for d in days:
        schedules_by_date[d].sort(key=lambda x: x.start_time)

    shifts_by_weekday: dict[int, list[WeeklyShift]] = {i: [] for i in range(7)}
    for shift in shifts:
        shifts_by_weekday[shift.weekday].append(shift)

    selected_day_shifts = shifts_by_weekday[selected_date.weekday()]
    prev_week = week_start - timedelta(days=7)
    next_week = week_start + timedelta(days=7)
    prev_selected_date = selected_date - timedelta(days=7)
    next_selected_date = selected_date + timedelta(days=7)

    weekday_labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    return render_template(
        "doctor/weekly.html",
        form=form,
        shifts=shifts,
        days=days,
        schedules_by_date=schedules_by_date,
        shifts_by_weekday=shifts_by_weekday,
        selected_date=selected_date,
        selected_day_shifts=selected_day_shifts,
        week_start=week_start,
        week_end=week_end,
        prev_week=prev_week,
        next_week=next_week,
        prev_selected_date=prev_selected_date,
        next_selected_date=next_selected_date,
        week_options=week_options,
        selected_apply_weeks=selected_apply_weeks,
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
    _, delete_message = ScheduleService.delete_week_template_and_schedule(shift=shift)
    flash("Weekly template deleted for this week", "info")
    if delete_message:
        flash(delete_message, "warning")
    redirect_params = {
        "week_start": request.form.get("week_start") or _start_of_week(date.today()).isoformat(),
        "selected_date": request.form.get("selected_date") or date.today().isoformat(),
    }
    if _is_admin():
        redirect_params["doctor_id"] = shift.doctor_id
    return redirect(url_for("doctor.weekly", **redirect_params))


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

