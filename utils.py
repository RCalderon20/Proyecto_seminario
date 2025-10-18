# app/utils.py
from __future__ import annotations  # Debe ser la PRIMERA línea

from functools import wraps
from typing import Optional, Union
import binascii
import hashlib
import hmac

from flask import session, redirect, url_for, flash, request


# ================================
# Parámetros PBKDF2 del proyecto
# ================================
PBKDF2_ITER = 200_000   # Iteraciones canónicas
PBKDF2_DKLEN = 32       # Longitud del hash (bytes)


# ================================
# Decoradores de acceso
# ================================
def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            flash("Debes iniciar sesión para continuar.", "warning")
            return redirect(url_for("auth.login_form", next=request.path))
        return view(*args, **kwargs)
    return wrapper


def roles_required(*roles):
    """
    Uso:
      @roles_required("Administrador")  # o varios: ("Administrador","Técnico")
    """
    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            user_roles = session.get("roles") or []
            if not any(r in user_roles for r in roles):
                flash("No tienes permisos para acceder a esta sección.", "danger")
                return redirect(url_for("catalog.home"))
            return view(*args, **kwargs)
        return wrapper
    return decorator


def is_admin() -> bool:
    return "Administrador" in (session.get("roles") or [])


# ================================
# Utilidades de hash/bytes
# ================================
def to_bytes_from_varbinary_or_hex(value):
    if value is None:
        return None
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value)
    if isinstance(value, str):
        s = value.strip()
        if s.lower().startswith("0x"):
            try:
                return binascii.unhexlify(s[2:])
            except (binascii.Error, ValueError):
                return None
        try:
            return s.encode("utf-8")
        except Exception:
            return None
    return None


def pbkdf2_hash_password(
    password: str,
    salt: bytes,
    iterations: int = PBKDF2_ITER,
    dklen: int = PBKDF2_DKLEN,
) -> bytes:
    """Genera el hash PBKDF2-HMAC-SHA256."""
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations, dklen)


def verify_password(
    password: str,
    stored_hash: bytes,
    salt: bytes,
) -> bool:
    """
    Verifica la contraseña contra el hash almacenado.

    1) Intenta con los parámetros canónicos (200k iteraciones).
    2) Si no coincide, intenta con 120k (compatibilidad con cuentas antiguas).
    """
    try:
        # Intento canónico (200k)
        new_hash = pbkdf2_hash_password(password, salt, PBKDF2_ITER, PBKDF2_DKLEN)
        if hmac.compare_digest(new_hash, stored_hash):
            return True

        # Intento legado (120k)
        legacy_hash = pbkdf2_hash_password(password, salt, 120_000, PBKDF2_DKLEN)
        return hmac.compare_digest(legacy_hash, stored_hash)
    except Exception:
        return False
