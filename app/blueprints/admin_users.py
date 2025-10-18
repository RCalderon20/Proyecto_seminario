# app/blueprints/admin_users.py
from flask import Blueprint, render_template, request, redirect, url_for, flash
from utils import login_required, roles_required
from ..db import (
    admin_users_list, admin_user_get, admin_user_create, admin_user_update,
    admin_user_hard_delete, admin_user_set_active, admin_user_reset_password,
    roles_get_all
)
from ..db import admin_user_create_with_roles

bp = Blueprint("admin_users", __name__, url_prefix="/admin/users")

# ======= LISTADO =======
@bp.get("/")
@login_required
@roles_required("Administrador")
def list_users():
    q = (request.args.get("q") or "").strip()
    rows = admin_users_list(q)
    return render_template("admin_users_list.html", rows=rows, q=q)

# ======= CREAR =======
@bp.get("/new")
@login_required
@roles_required("Administrador")
def new_user():
    roles = roles_get_all()
    return render_template("admin_users_form.html", mode="new", roles=roles, user=None, user_role_ids=[])

@bp.post("/new")
@login_required
@roles_required("Administrador")
def new_user_post():
    from flask import request, redirect, url_for, flash

    email = (request.form.get("email") or "").strip().lower()
    first = (request.form.get("first_name") or "").strip()
    last  = (request.form.get("last_name") or "").strip()
    pwd   = request.form.get("password") or ""
    conf  = request.form.get("confirm") or ""
    active = 1 if request.form.get("active") == "on" else 0

    # recoge roles como lista (checkbox name="roles" value="1/2/3")
    role_ids = request.form.getlist("roles")  # ['1','2',...]

    if not email or not first or not last or not pwd or pwd != conf:
        flash("Completa los campos y asegúrate de que las contraseñas coincidan.", "danger")
        return redirect(url_for("admin_users.new_user"))

    try:
        user_id = admin_user_create_with_roles(email, first, last, pwd, bool(active), [int(r) for r in role_ids])
        flash("Usuario creado correctamente.", "success")
        return redirect(url_for("admin_users.edit_user", user_id=user_id))
    except Exception as e:
        flash(f"No se pudo crear: {e}", "danger")
        return redirect(url_for("admin_users.new_user"))


# ======= EDITAR =======
@bp.get("/<int:user_id>/edit")
@login_required
@roles_required("Administrador")
def edit_user(user_id: int):
    user, role_ids = admin_user_get(user_id)
    if not user:
        flash("Usuario no existe.", "warning")
        return redirect(url_for("admin_users.list_users"))
    roles = roles_get_all()
    return render_template("admin_users_form.html", mode="edit", roles=roles, user=user, user_role_ids=role_ids)

@bp.post("/<int:user_id>/edit")
@login_required
@roles_required("Administrador")
def edit_user_post(user_id: int):
    email = (request.form.get("email") or "").strip().lower()
    first = (request.form.get("first_name") or "").strip()
    last  = (request.form.get("last_name") or "").strip()
    is_active = 1 if request.form.get("is_active") == "on" else 0
    role_ids = [int(rid) for rid in request.form.getlist("roles") if str(rid).isdigit()]

    if not email or not first or not last:
        flash("Completa los campos obligatorios.", "warning")
        return redirect(url_for("admin_users.edit_user", user_id=user_id))

    try:
        admin_user_update(user_id, email, first, last, is_active, role_ids)
        flash("Usuario actualizado.", "success")
    except Exception as e:
        flash(f"No se pudo actualizar: {e}", "danger")
    return redirect(url_for("admin_users.edit_user", user_id=user_id))

# ======= ACTIVAR / DESACTIVAR =======
@bp.post("/<int:user_id>/toggle")
@login_required
@roles_required("Administrador")
def toggle_active(user_id: int):
    active = 1 if (request.form.get("active") == "1") else 0
    admin_user_set_active(user_id, active)
    flash("Estado actualizado.", "info")
    return redirect(url_for("admin_users.list_users"))

# ======= RESET PASSWORD (opcional) =======
@bp.post("/<int:user_id>/resetpw")
@login_required
@roles_required("Administrador")
def reset_password(user_id: int):
    newpw = request.form.get("new_password") or ""
    confirm = request.form.get("confirm") or ""
    if not newpw or newpw != confirm:
        flash("Contraseña inválida.", "warning")
    else:
        admin_user_reset_password(user_id, newpw)
        flash("Contraseña actualizada.", "success")
    return redirect(url_for("admin_users.edit_user", user_id=user_id))

# ======= ELIMINAR (borrado lógico recomendado) =======
@bp.post("/<int:user_id>/delete")
@login_required
@roles_required("Administrador")
def delete_user(user_id: int):
    try:
        admin_user_hard_delete(user_id)   # <-- ahora borra definitivamente
        flash("Usuario eliminado definitivamente.", "warning")
    except Exception as e:
        flash(f"No se pudo eliminar: {e}", "danger")
    return redirect(url_for("admin_users.list_users"))