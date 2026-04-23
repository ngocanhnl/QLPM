from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.models.enums import UserRole
from app.services.auth_service import AuthService
from app.services.forms import LoginForm, RegisterForm

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


def _redirect_after_login():
    next_url = request.args.get("next")
    if next_url:
        return redirect(next_url)
    if current_user.role == UserRole.DOCTOR:
        return redirect(url_for("doctor.dashboard"))
    if current_user.role == UserRole.ADMIN:
        return redirect(url_for("admin.dashboard"))
    return redirect(url_for("patient.dashboard"))


@auth_bp.get("/login")
@auth_bp.post("/login")
def login():
    if current_user.is_authenticated:
        return _redirect_after_login()

    form = LoginForm()
    if form.validate_on_submit():
        user = AuthService.authenticate(username=form.username.data.strip(), password=form.password.data)
        if not user:
            flash("Invalid username or password", "danger")
        else:
            AuthService.login(user)
            flash("Login successful", "success")
            return _redirect_after_login()

    return render_template("auth/login.html", form=form)


@auth_bp.get("/register")
@auth_bp.post("/register")
def register():
    if current_user.is_authenticated:
        return _redirect_after_login()

    form = RegisterForm()
    form.set_hospital_choices()
    if form.validate_on_submit():
        role = UserRole(form.role.data)
        try:
            AuthService.register_user(
                username=form.username.data.strip(),
                email=form.email.data.strip(),
                phone=form.phone.data.strip(),
                password=form.password.data,
                role=role,
                specialty=(form.specialty.data or None),
                hospital_id=(form.hospital_id.data or None),
                description=(form.description.data or None),
                experience_years=(form.experience_years.data or 0),
            )
        except ValueError as e:
            flash(str(e), "danger")
            return render_template("auth/register.html", form=form)

        flash("Account created. Please login.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/register.html", form=form)


@auth_bp.post("/logout")
@login_required
def logout():
    AuthService.logout()
    flash("Logged out", "info")
    return redirect(url_for("patient.search"))

