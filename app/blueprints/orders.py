from flask import Blueprint, request, redirect, url_for, render_template, flash, session, abort
from ..db import (
    exec_sp_create_order_from_cart,
    orders_get_history,
    user_orders,
    user_order_header,
    user_order_items
)

bp = Blueprint("orders", __name__, url_prefix="/orders")

GUEST_USER_ID = None  # con login ya no usamos invitado para historial


# =============================
#  HISTORIAL DE PEDIDOS (antiguo /history)
# =============================
@bp.get("/history")
def history():
    user_id = session.get("user_id")
    if not user_id:
        flash("Inicia sesión para ver tu historial.", "warning")
        return redirect(url_for("auth.login_form"))
    orders = orders_get_history(user_id)
    return render_template("orders_history.html", orders=orders)


# =============================
#  NUEVO: MÓDULO “MIS PEDIDOS”
# =============================

def _require_login():
    """Verifica si hay sesión activa."""
    usr = session.get("user")
    if not usr:
        flash("Inicia sesión para ver tus pedidos.", "warning")
        return None
    return usr


@bp.get("/")
def my_orders():
    """Lista de pedidos del usuario actual."""
    usr = _require_login()
    if usr is None:
        return redirect(url_for("auth.login_form"))
    uid = int(usr["UserId"])
    orders = user_orders(uid)
    return render_template("my_orders.html", orders=orders)


@bp.get("/<int:order_id>")
def order_detail(order_id: int):
    """Detalle de un pedido específico."""
    usr = _require_login()
    if usr is None:
        return redirect(url_for("auth.login_form"))
    uid = int(usr["UserId"])

    header = user_order_header(order_id, uid)
    if not header:
        abort(404)

    items = user_order_items(order_id, uid)
    return render_template("order_detail.html", order=header, items=items)


# =============================
#  CHECKOUT (procesar pedido)
# =============================
@bp.post("/checkout")
def checkout():
    """Convierte el carrito en pedido."""
    cart_id_str = (request.form.get("cartId") or "").strip()
    cart_id = int(cart_id_str) if cart_id_str.isdigit() else session.get("cart_id")
    if not cart_id:
        flash("No se encontró el carrito para procesar el pedido.", "danger")
        return redirect(url_for("cart.view_cart"))

    user_id = session.get("user_id") or GUEST_USER_ID

    try:
        order_id = exec_sp_create_order_from_cart(cart_id, user_id)
        return render_template("order_success.html", order_id=order_id)
    except Exception as e:
        flash(f"Error al procesar pedido: {e}", "danger")
        return redirect(url_for("cart.view_cart"))
