from flask import Blueprint, request, render_template, redirect, url_for, session, flash
from ..db import (
    get_or_create_cart,       # asegúrate que este helper existe en tu db.py
    cart_add_item,
    cart_get_items,
    cart_update_qty,
    cart_remove_item,
    cart_clear
)

bp = Blueprint("cart", __name__, url_prefix="/cart")

def _ensure_session_cart() -> int:
    cart_id = session.get("cart_id")
    cart_id = get_or_create_cart(cart_id)   # reutiliza o crea carrito
    session["cart_id"] = cart_id
    return cart_id

@bp.get("/")
def view_cart():
    cart_id = _ensure_session_cart()
    items, subtotal = cart_get_items(cart_id)
    iva = round(subtotal - (subtotal / 1.12), 2) if subtotal else 0.0
    total = round(subtotal, 2)

    # 👇 Nada de direcciones aquí
    return render_template(
        "cart.html",
        items=items,
        subtotal=subtotal,
        iva=iva,
        total=total,
        cart_id=cart_id
    )

@bp.post("/add")
def add():
    cart_id = _ensure_session_cart()
    try:
        product_id = int(request.form.get("productId", "0"))
        qty = int(request.form.get("qty", "1"))
        cart_add_item(cart_id, product_id, qty)
        flash("Producto agregado al carrito.", "success")
    except Exception as e:
        flash(f"No se pudo agregar: {e}", "danger")
    return redirect(request.referrer or url_for("catalog.home"))

@bp.post("/update")
def update():
    try:
        cart_item_id = int(request.form.get("cartItemId", "0"))
        qty = int(request.form.get("qty", "1"))
        cart_update_qty(cart_item_id, qty)
        flash("Cantidad actualizada.", "info")
    except Exception as e:
        flash(f"No se pudo actualizar: {e}", "danger")
    return redirect(url_for("cart.view_cart"))

@bp.post("/remove")
def remove():
    try:
        cart_item_id = int(request.form.get("cartItemId", "0"))
        cart_remove_item(cart_item_id)
        flash("Producto eliminado del carrito.", "warning")
    except Exception as e:
        flash(f"No se pudo eliminar: {e}", "danger")
    return redirect(url_for("cart.view_cart"))

@bp.post("/clear")
def clear():
    try:
        cart_id = _ensure_session_cart()
        cart_clear(cart_id)
        flash("Carrito vaciado.", "warning")
    except Exception as e:
        flash(f"No se pudo vaciar: {e}", "danger")
    return redirect(url_for("cart.view_cart"))
