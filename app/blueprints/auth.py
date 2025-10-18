# app/blueprints/auth.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, session

# Helpers de BD
from ..db import user_get_by_email, user_create, fetch_one, fetch_all

import hmac
import hashlib  # si usas _pbkdf2_sha256 para pruebas

# >>> IMPORT RELATIVO CORRECTO <<<
from utils import (
    to_bytes_from_varbinary_or_hex,
    pbkdf2_hash_password,
    PBKDF2_ITER,
    PBKDF2_DKLEN,
)

bp = Blueprint("auth", __name__, url_prefix="/auth")


@bp.get("/login")
def login_form():
    return render_template("login.html")


def _pbkdf2_sha256(password: str, salt_bytes: bytes, iterations: int = 200_000) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt_bytes, iterations)


@bp.post("/login")
def login_post():
    email = (request.form.get("email") or "").strip().lower()
    password = (request.form.get("password") or "").strip()

    if not email or not password:
        flash("Ingresa email y contraseña.", "warning")
        return redirect(url_for("auth.login_form"))

    # 1️⃣ Buscar el usuario
    row = fetch_one(
        """
        SELECT TOP 1
            u.UserId, u.Email, u.FirstName, u.LastName, u.IsActive,
            u.PasswordHash, u.PasswordSalt
        FROM dbo.Users u
        WHERE LOWER(u.Email) = ?
        """,
        (email,),
    )

    if not row:
        flash("Credenciales inválidas.", "danger")
        return redirect(url_for("auth.login_form"))

    if not row["IsActive"]:
        flash("Tu cuenta está inactiva.", "warning")
        return redirect(url_for("auth.login_form"))

    # 2️⃣ Convertir valores VARBINARY/hex a bytes
    stored_hash = to_bytes_from_varbinary_or_hex(row["PasswordHash"])
    stored_salt = to_bytes_from_varbinary_or_hex(row["PasswordSalt"])

    if not stored_hash or not stored_salt:
        flash("No se puede verificar la contraseña (hash/salt inválidos).", "danger")
        return redirect(url_for("auth.login_form"))

    # 🔍 Diagnóstico detallado
    print("======= DIAGNÓSTICO DE LOGIN =======")
    print("Email:", email)
    print("HASH len:", len(stored_hash), "SALT len:", len(stored_salt))
    print("HASH (hex):", stored_hash.hex()[:64] + "...")
    print("SALT (hex):", stored_salt.hex())

    from utils import pbkdf2_hash_password  # asegúrate de que apunta al tuyo real

    candidatos = [50_000, 100_000, 120_000, 150_000, 200_000, 240_000, 300_000]
    match_iter = None
    for it in candidatos:
        h = pbkdf2_hash_password(password, stored_salt, it, 32)
        igual = (h == stored_hash)
        print(f"iter={it} -> match={igual}")
        if igual:
            match_iter = it
            break

    # Intento alternativo por si dklen=64
    if not match_iter:
        for it in [120_000, 200_000]:
            h64 = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), stored_salt, it, 64)
            first32_match = (h64[:32] == stored_hash)
            all64_match = (len(stored_hash) == 64 and h64 == stored_hash)
            print(f"[dklen=64] iter={it} -> first32_match={first32_match}, all64_match={all64_match}")

    print("====================================")

    if not match_iter:
        flash("Credenciales inválidas.", "danger")
        return redirect(url_for("auth.login_form"))

    # 3️⃣ Autenticación exitosa
    session.clear()
    session["user_id"] = int(row["UserId"])
    session["user_name"] = f"{row['FirstName']} {row['LastName']}".strip()

    # Cargar roles
    roles_rows = fetch_all(
        """
        SELECT r.Name
        FROM dbo.UserRoles ur
        JOIN dbo.Roles r ON r.RoleId = ur.RoleId
        WHERE ur.UserId = ?
        """,
        (row["UserId"],),
    )
    session["roles"] = [r["Name"] for r in roles_rows] if roles_rows else []

    flash("¡Bienvenido!", "success")
    return redirect(url_for("catalog.home"))



@bp.get("/register")
def register_form():
    return render_template("register.html")


@bp.post("/register")
def register_post():
    email = (request.form.get("email") or "").strip().lower()
    first = (request.form.get("first_name") or "").strip()
    last  = (request.form.get("last_name") or "").strip()
    password = request.form.get("password") or ""
    confirm  = request.form.get("confirm") or ""

    if not email or not first or not last or not password or password != confirm:
        flash("Completa los campos y asegúrate de que las contraseñas coincidan.", "danger")
        return redirect(url_for("auth.register_form"))

    if user_get_by_email(email):
        flash("El correo ya está registrado.", "warning")
        return redirect(url_for("auth.register_form"))

    uid = user_create(email, first, last, password)
    if not uid:
        flash("No se pudo crear el usuario. Inténtalo de nuevo.", "danger")
        return redirect(url_for("auth.register_form"))

    session["user_id"] = uid
    session["user_name"] = first
    session["roles"] = []
    flash("Registro completo. ¡Bienvenido!", "success")
    return redirect(url_for("catalog.home"))


@bp.post("/logout")
def logout():
    session.pop("user_id", None)
    session.pop("user_name", None)
    session.pop("roles", None)
    flash("Sesión cerrada.", "info")
    return redirect(url_for("catalog.home"))
