from flask import Blueprint, render_template, session, redirect, url_for, flash
from ..db import notifications_get_all, notifications_mark_read

bp = Blueprint("notifications", __name__, url_prefix="/notifications")

@bp.get("/")
def view_all():
    user_id = session.get("user_id")
    if not user_id:
        flash("Debes iniciar sesión para ver tus notificaciones.", "warning")
        return redirect(url_for("auth.login_form"))
    notifications = notifications_get_all(user_id)
    return render_template("notifications.html", notifications=notifications)

@bp.post("/read/<int:notification_id>")
def mark_read(notification_id: int):
    notifications_mark_read(notification_id)
    flash("Notificación marcada como leída.", "info")
    return redirect(url_for("notifications.view_all"))
