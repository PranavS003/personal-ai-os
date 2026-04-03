from flask import Blueprint, redirect, render_template, request, session, url_for

from services import VALID_USERS, get_current_user

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip().lower()
        password = request.form.get("password") or ""

        # Keep credential checks on the server so passwords never live in frontend JS.
        if VALID_USERS.get(username) == password:
            session.clear()
            session["user"] = username
            return redirect(url_for("onboarding.home"))

        return render_template("login.html", error="Invalid credentials")

    if get_current_user():
        return redirect(url_for("onboarding.home"))

    return render_template("login.html", error=None)


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
