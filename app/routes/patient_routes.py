from datetime import date, timedelta

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.models.enums import AppointmentStatus, PaymentStatus, UserRole
from app.models.appointment import Appointment
from app.models.doctor_review import DoctorReview
from app.models.payment_transaction import PaymentTransaction
from app.models.schedule import Schedule
from app.models.user import User
from app.services.appointment_service import AppointmentService
from app.services.doctor_service import DoctorService
from app.services.review_service import DoctorReviewService
from app.services.vnpay_service import VnpayService
from app.services.forms import BookingForm, DoctorReviewForm, NewAppointmentForm, PatientContactForm, SearchDoctorForm
from app.services.authz import roles_required

patient_bp = Blueprint("patient", __name__)


def _target_patient_id() -> int:
    if current_user.role != UserRole.ADMIN:
        return current_user.id
    patient_id = request.args.get("patient_id", type=int) or request.form.get("patient_id", type=int)
    if patient_id:
        patient = db.session.get(User, patient_id)
        if patient and patient.role == UserRole.PATIENT:
            return patient_id
    first_patient = db.session.execute(
        db.select(User).where(User.role == UserRole.PATIENT).order_by(User.id.asc())
    ).scalars().first()
    return first_patient.id if first_patient else current_user.id


@patient_bp.get("/")
def home():
    return redirect(url_for("patient.search"))


@patient_bp.get("/doctors/search")
@patient_bp.post("/doctors/search")
def search():
    form = SearchDoctorForm()
    doctor_name = request.args.get("doctor_name") if request.method == "GET" else form.doctor_name.data
    hospital_name = request.args.get("hospital_name") if request.method == "GET" else form.hospital_name.data
    specialty = request.args.get("specialty") if request.method == "GET" else form.specialty.data
    result_hospital = request.args.get("result_hospital") if request.method == "GET" else None
    result_specialty = request.args.get("result_specialty") if request.method == "GET" else None

    if request.method == "POST" and form.validate_on_submit():
        params: dict[str, str | int] = {}
        doctor_name_value = (form.doctor_name.data or "").strip()
        if doctor_name_value:
            params["doctor_name"] = doctor_name_value
        hospital_name_value = (form.hospital_name.data or "").strip()
        if hospital_name_value:
            params["hospital_name"] = hospital_name_value
        specialty_value = (form.specialty.data or "").strip()
        if specialty_value:
            params["specialty"] = specialty_value
        return redirect(url_for("patient.search", **params))

    if request.method == "GET":
        doctor_name = (doctor_name or "").strip()
        hospital_name = (hospital_name or "").strip()
        specialty = (specialty or "").strip()
        result_hospital = (result_hospital or "").strip()
        result_specialty = (result_specialty or "").strip()
        form.doctor_name.data = (doctor_name or "").strip()
        form.hospital_name.data = (hospital_name or "").strip()
        form.specialty.data = (specialty or "").strip()

    if not doctor_name:
        result_hospital = ""
        result_specialty = ""

    base_params: dict[str, str | int] = {}
    if doctor_name:
        base_params["doctor_name"] = doctor_name
    if hospital_name:
        base_params["hospital_name"] = hospital_name
    if specialty:
        base_params["specialty"] = specialty

    doctors = DoctorService.search_doctors(
        doctor_name=doctor_name,
        hospital_name=hospital_name,
        specialty=specialty,
        exact_hospital_name=result_hospital or None,
        exact_specialty=result_specialty or None,
    )

    name_search_doctors = []
    if doctor_name:
        name_search_doctors = DoctorService.search_doctors(
            doctor_name=doctor_name,
        )
    filtered_hospitals = sorted({d.hospital.name for d in name_search_doctors if d.hospital and d.hospital.name})
    filtered_specialties = sorted({d.specialty for d in name_search_doctors if d.specialty})

    specialties = DoctorService.list_specialties()
    hospitals = DoctorService.list_hospitals()
    doctor_names = DoctorService.list_doctor_names()
    return render_template(
        "patient/search_doctor.html",
        form=form,
        doctors=doctors,
        specialties=specialties,
        hospitals=hospitals,
        doctor_names=doctor_names,
        filtered_hospitals=filtered_hospitals,
        filtered_specialties=filtered_specialties,
        selected_result_hospital=result_hospital or "",
        selected_result_specialty=result_specialty or "",
        base_query_params=base_params,
        selected_specialty=(specialty or "").strip(),
    )


@patient_bp.get("/doctors/<int:doctor_id>")
def doctor_detail(doctor_id: int):
    doctor = DoctorService.get_doctor(doctor_id)
    if not doctor:
        abort(404)
    schedules = DoctorService.get_available_schedules(doctor_id=doctor_id, from_date=date.today())
    rating_avg, rating_count, rating_avg_rounded = DoctorReviewService.get_rating_summary_for_doctor(doctor_id=doctor.id)
    reviews = DoctorReviewService.list_reviews_for_doctor(doctor_id=doctor.id, limit=10)
    return render_template(
        "patient/doctor_detail.html",
        doctor=doctor,
        schedules=schedules,
        rating_avg=rating_avg,
        rating_count=rating_count,
        rating_avg_rounded=rating_avg_rounded,
        reviews=reviews,
    )


@patient_bp.get("/appointments/new")
@patient_bp.post("/appointments/new")
@login_required
@roles_required(UserRole.PATIENT)
def appointment_new():
    form = NewAppointmentForm()
    patient_id = _target_patient_id()

    hospital_id = request.args.get("hospital_id", type=int) if request.method == "GET" else None
    doctor_id = request.args.get("doctor_id", type=int) if request.method == "GET" else None
    date_value = request.args.get("date", type=str) if request.method == "GET" else None

    hospitals = DoctorService.list_hospital_options()
    form.hospital_id.choices = [("", "All hospitals")] + [(str(h_id), h_name) for h_id, h_name in hospitals]
    doctor_options = DoctorService.list_doctor_options(hospital_id=hospital_id)
    form.doctor_id.choices = [("", "Select doctor")] + [(str(d_id), d_name) for d_id, d_name in doctor_options]

    if request.method == "POST" and form.validate_on_submit():
        params: dict[str, str] = {}
        if form.hospital_id.data:
            params["hospital_id"] = str(form.hospital_id.data)
        if form.doctor_id.data:
            params["doctor_id"] = str(form.doctor_id.data)
        if form.date.data:
            params["date"] = form.date.data.isoformat()
        if current_user.role == UserRole.ADMIN:
            params["patient_id"] = str(patient_id)
        return redirect(url_for("patient.appointment_new", **params))

    if request.method == "GET":
        form.hospital_id.data = str(hospital_id) if hospital_id else ""
        form.doctor_id.data = str(doctor_id) if doctor_id else ""
        if date_value:
            try:
                form.date.data = date.fromisoformat(date_value)
            except ValueError:
                pass

    schedules = []
    schedules_by_date: dict[date, list] = {}
    selected_doctor = None
    if doctor_id:
        selected_doctor = DoctorService.get_doctor(doctor_id)
        if selected_doctor:
            if date_value:
                schedules = DoctorService.get_available_schedules(doctor_id=doctor_id, from_date=form.date.data)
                if form.date.data:
                    schedules = [s for s in schedules if s.date == form.date.data]
            else:
                end_date = date.today() + timedelta(days=6)
                schedules = DoctorService.get_available_schedules(doctor_id=doctor_id, from_date=date.today())
                schedules = [s for s in schedules if s.date <= end_date]
                for s in schedules:
                    schedules_by_date.setdefault(s.date, []).append(s)
                for d in schedules_by_date:
                    schedules_by_date[d].sort(key=lambda x: x.start_time)

    return render_template(
        "patient/new_appointment.html",
        form=form,
        schedules=schedules,
        schedules_by_date=schedules_by_date,
        selected_doctor=selected_doctor,
    )

@patient_bp.get("/book/<int:schedule_id>")
@patient_bp.post("/book/<int:schedule_id>")
@login_required
@roles_required(UserRole.PATIENT)
def book(schedule_id: int):
    form = BookingForm()
    schedule = Schedule.query.get(schedule_id)
    patient_id = _target_patient_id()

    if schedule is None:
        abort(404)

    # Payment amount is based on the selected doctor's booking price.
    amount = float(getattr(schedule.doctor, "price_vnd", None) or 500000)

    self_info = {
        "fullname": current_user.username,
        "email": (getattr(current_user, "email", "") or "").strip(),
        "phone": (getattr(current_user, "phone", "") or "").strip(),
        "symptoms": "",
    }
    self_missing_email = not self_info["email"]
    self_missing_phone = not self_info["phone"]
    self_requires_contact = self_missing_email or self_missing_phone

    if request.method == "GET":
        form.booking_for.data = "self"
        form.fullname.data = self_info["fullname"]
        form.email.data = self_info["email"]
        form.phone.data = self_info["phone"]
        form.symptoms.data = self_info["symptoms"]

    if form.validate_on_submit():
        booking_for = form.booking_for.data
        contact_fullname = (form.fullname.data or "").strip()
        contact_email = (form.email.data or "").strip() or None
        contact_phone = (form.phone.data or "").strip()
        symptoms = (form.symptoms.data or "").strip() or None

        if booking_for == "self":
            contact_fullname = self_info["fullname"]
            if self_missing_email:
                contact_email = (form.email.data or "").strip() or None
            else:
                contact_email = self_info["email"] or None
            if self_missing_phone:
                contact_phone = (form.phone.data or "").strip()
            else:
                contact_phone = self_info["phone"] or ""

            if not contact_email:
                form.email.errors.append("Vui long bo sung email de dat lich cho ban than.")
                return render_template(
                    "patient/booking.html",
                    form=form,
                    schedule_id=schedule_id,
                    amount=amount,
                    schedule=schedule,
                    self_info=self_info,
                    self_missing_email=self_missing_email,
                    self_missing_phone=self_missing_phone,
                    self_requires_contact=self_requires_contact,
                )
            if not contact_phone:
                form.phone.errors.append("Vui long bo sung so dien thoai de dat lich cho ban than.")
                return render_template(
                    "patient/booking.html",
                    form=form,
                    schedule_id=schedule_id,
                    amount=amount,
                    schedule=schedule,
                    self_info=self_info,
                    self_missing_email=self_missing_email,
                    self_missing_phone=self_missing_phone,
                    self_requires_contact=self_requires_contact,
                )

            # Persist missing contact information to the logged-in account.
            if self_missing_email:
                current_user.email = contact_email
                self_info["email"] = contact_email
            if self_missing_phone:
                current_user.phone = contact_phone
                self_info["phone"] = contact_phone

        if AppointmentService.has_duplicate_person_booking(
            patient_id=patient_id,
            booking_for=booking_for,
            contact_email=contact_email,
            contact_phone=contact_phone,
            date_value=schedule.date,
            start_time=schedule.start_time,
            end_time=schedule.end_time,
        ):
            flash("Người được đặt đã có lịch hẹn trùng khung giờ này.", "danger")
            return render_template(
                "patient/booking.html",
                form=form,
                schedule_id=schedule_id,
                amount=amount,
                schedule=schedule,
                self_info=self_info,
                self_missing_email=self_missing_email,
                self_missing_phone=self_missing_phone,
                self_requires_contact=self_requires_contact,
            )

        ip_addr = (
            request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
            or request.remote_addr
            or "127.0.0.1"
        )

        txn_ref = VnpayService.generate_txn_ref()

        # VNPay order info: must be ASCII, no accents/special characters (demo).
        order_info = f"Thanh toan don hang {txn_ref}"

        transaction = PaymentTransaction(
            patient_id=patient_id,
            schedule_id=schedule_id,
            booking_for=booking_for,
            contact_fullname=contact_fullname,
            contact_email=contact_email,
            contact_phone=contact_phone,
            symptoms=symptoms,
            vnp_txn_ref=txn_ref,
            amount_vnd=int(amount),
            status=PaymentStatus.PENDING,
        )
        db.session.add(transaction)
        db.session.commit()

        try:
            payment_url = VnpayService.create_payment_url(
                payment_url=current_app.config["VNPAY_PAYMENT_URL"],
                tmn_code=current_app.config["VNPAY_TMN_CODE"],
                hash_secret=current_app.config["VNPAY_HASH_SECRET"],
                return_url=url_for("patient.vnpay_return", _external=True),
                ip_addr=ip_addr,
                locale=current_app.config["VNPAY_LOCALE"],
                curr_code=current_app.config["VNPAY_CURR_CODE"],
                order_type=current_app.config["VNPAY_ORDER_TYPE"],
                txn_ref=txn_ref,
                amount_vnd=int(amount),
                order_info=order_info,
                version=current_app.config["VNPAY_VERSION"],
            )
        except Exception:
            transaction.status = PaymentStatus.FAILED
            db.session.commit()
            flash("Failed to create VNPay payment URL.", "danger")
            return render_template(
                "patient/booking.html",
                form=form,
                schedule_id=schedule_id,
                amount=amount,
                schedule=schedule,
                self_info=self_info,
                self_missing_email=self_missing_email,
                self_missing_phone=self_missing_phone,
                self_requires_contact=self_requires_contact,
            )

        return redirect(payment_url)

    return render_template(
        "patient/booking.html",
        form=form,
        schedule_id=schedule_id,
        amount=amount,
        schedule=schedule,
        self_info=self_info,
        self_missing_email=self_missing_email,
        self_missing_phone=self_missing_phone,
        self_requires_contact=self_requires_contact,
    )


@patient_bp.get("/payment-result")
def vnpay_return():
    # VNPay callback: no CSRF needed, we validate VNPay signature.
    params = request.args.to_dict(flat=True)
    provided_secure_hash = params.get("vnp_SecureHash", "")
    vnp_txn_ref = params.get("vnp_TxnRef", "")
    response_code = params.get("vnp_ResponseCode", "")

    secure_valid = VnpayService.verify_return(
        hash_secret=current_app.config["VNPAY_HASH_SECRET"],
        vnp_params=params,
        provided_secure_hash=provided_secure_hash,
    )

    if not vnp_txn_ref:
        flash("Payment callback missing txn ref.", "danger")
        return redirect(url_for("auth.login"))

    transaction = db.session.execute(
        db.select(PaymentTransaction).where(PaymentTransaction.vnp_txn_ref == vnp_txn_ref)
    ).scalar_one_or_none()

    if not transaction:
        flash("Payment transaction not found.", "danger")
        return redirect(url_for("auth.login"))

    if transaction.status == PaymentStatus.SUCCESS:
        flash("Payment already processed.", "info")
        return redirect(url_for("patient.dashboard"))

    if secure_valid and response_code == "00":
        try:
            AppointmentService.book(
                patient_id=transaction.patient_id,
                schedule_id=transaction.schedule_id,
                booking_for=transaction.booking_for,
                contact_fullname=transaction.contact_fullname,
                contact_email=transaction.contact_email,
                contact_phone=transaction.contact_phone,
                symptoms=transaction.symptoms,
                status=AppointmentStatus.PENDING,
            )
            transaction.status = PaymentStatus.SUCCESS
            db.session.commit()
        except ValueError as e:
            transaction.status = PaymentStatus.FAILED
            db.session.commit()
            flash(f"Payment received but appointment could not be created: {e}", "danger")
            return redirect(url_for("patient.dashboard"))

        flash("Payment successful. Appointment created (PENDING).", "success")
        return redirect(url_for("patient.dashboard"))

    transaction.status = PaymentStatus.FAILED
    db.session.commit()
    flash("Payment failed or invalid signature.", "danger")
    return redirect(url_for("patient.dashboard"))


@patient_bp.get("/patient/dashboard")
@login_required
@roles_required(UserRole.PATIENT)
def dashboard():
    patient_id = _target_patient_id()
    appts = AppointmentService.list_for_patient(patient_id=patient_id)
    appt_ids = [a.id for a in appts]
    schedule_ids = [a.schedule_id for a in appts]

    paid_schedule_ids: set[int] = set()
    if schedule_ids:
        paid_schedule_ids = set(
            db.session.execute(
                db.select(PaymentTransaction.schedule_id)
                .where(
                    PaymentTransaction.patient_id == patient_id,
                    PaymentTransaction.schedule_id.in_(schedule_ids),
                    PaymentTransaction.status == PaymentStatus.SUCCESS,
                )
            ).scalars().all()
        )

    reviewed_appointment_ids: set[int] = set()
    if appt_ids:
        reviewed_appointment_ids = set(
            db.session.execute(
                db.select(DoctorReview.appointment_id).where(
                    DoctorReview.patient_id == patient_id, DoctorReview.appointment_id.in_(appt_ids)
                )
            ).scalars().all()
        )

    review_meta: dict[int, dict[str, bool]] = {}
    for a in appts:
        paid = a.schedule_id in paid_schedule_ids
        reviewed = a.id in reviewed_appointment_ids
        can_review = paid and (not reviewed) and a.status.value != "CANCELLED"
        review_meta[a.id] = {"can_review": bool(can_review), "reviewed": bool(reviewed)}

    return render_template("patient/dashboard.html", appointments=appts, review_meta=review_meta)


@patient_bp.get("/appointments/<int:appointment_id>/review")
@patient_bp.post("/appointments/<int:appointment_id>/review")
@login_required
@roles_required(UserRole.PATIENT)
def appointment_review(appointment_id: int):
    appt = db.session.get(Appointment, appointment_id)
    if not appt:
        abort(404)

    if current_user.role != UserRole.ADMIN and appt.patient_id != current_user.id:
        abort(404)

    patient_id = appt.patient_id

    existing = DoctorReviewService.get_review_by_appointment_id(appointment_id=appointment_id)
    paid = (
        db.session.execute(
            db.select(PaymentTransaction.id)
            .where(
                PaymentTransaction.patient_id == patient_id,
                PaymentTransaction.schedule_id == appt.schedule_id,
                PaymentTransaction.status == PaymentStatus.SUCCESS,
            )
            .limit(1)
        ).scalar_one_or_none()
        is not None
    )

    if existing:
        flash("Bạn đã đánh giá lịch hẹn này rồi.", "info")
        return redirect(url_for("patient.dashboard"))

    if not paid or appt.status.value == "CANCELLED":
        flash("Bạn chỉ có thể đánh giá bác sĩ sau khi thanh toán thành công.", "warning")
        return redirect(url_for("patient.dashboard"))

    form = DoctorReviewForm()
    if request.method == "POST" and form.validate_on_submit():
        try:
            DoctorReviewService.create_review(
                appointment_id=appointment_id,
                patient_id=patient_id,
                stars=form.stars.data,
                comment=form.comment.data,
            )
            flash("Cảm ơn bạn đã đánh giá!", "success")
            return redirect(url_for("patient.dashboard"))
        except (ValueError, PermissionError) as e:
            flash(str(e), "danger")
        except Exception:
            flash("Gửi đánh giá thất bại, vui lòng thử lại.", "danger")

    return render_template("patient/appointment_review.html", appointment=appt, form=form)


@patient_bp.get("/patient/profile")
@patient_bp.post("/patient/profile")
@login_required
@roles_required(UserRole.PATIENT)
def profile():
    patient_id = _target_patient_id()
    appts = AppointmentService.list_for_patient(patient_id=patient_id)
    form = PatientContactForm()
    if request.method == "GET":
        form.email.data = (getattr(current_user, "email", "") or "").strip()
        form.phone.data = (getattr(current_user, "phone", "") or "").strip()
    if form.validate_on_submit():
        current_user.email = (form.email.data or "").strip() or None
        current_user.phone = (form.phone.data or "").strip() or None
        db.session.commit()
        flash("Cap nhat email/so dien thoai thanh cong.", "success")
        return redirect(url_for("patient.profile"))

    return render_template("patient/profile.html", appointments=appts, form=form)

