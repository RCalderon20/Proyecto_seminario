# app/blueprints/admin_products.py
from flask import Blueprint, render_template, request, redirect, url_for, flash
from utils import login_required, roles_required
from ..db import fetch_all, fetch_one, execute, execute_returning_id

bp = Blueprint("admin_products", __name__, url_prefix="/admin/products")

def _get_categories():
    return fetch_all("SELECT CategoryId, Name FROM dbo.Categories WHERE Active=1 ORDER BY Name")

def _to_int_or_none(v):
    v = (v or "").strip()
    return int(v) if v.isdigit() else None

def _exists_category(cid: int) -> bool:
    r = fetch_one("SELECT 1 AS ok FROM dbo.Categories WHERE CategoryId = ?", (cid,))
    return bool(r)

def _to_num(v):
    try:
        return float(v) if (v is not None and f"{v}".strip() != "") else None
    except Exception:
        return None


# === Material: crear/obtener automáticamente ===
def _get_material_by_name(name: str):
    return fetch_one("SELECT TOP 1 MaterialId FROM dbo.Materials WHERE Name = ?", (name,))

def _create_material(name: str, description: str | None = None) -> int:
    return execute_returning_id("""
        INSERT INTO dbo.Materials (Name, Description, Active, CreatedAt)
        OUTPUT INSERTED.MaterialId
        VALUES (?, ?, 1, SYSUTCDATETIME());
    """, (name, description))

def _get_or_create_material_id(name: str, description: str | None = None) -> int:
    row = _get_material_by_name(name)
    return int(row["MaterialId"]) if row else _create_material(name, description)

def _ensure_default_material() -> int:
    # nombre del material por defecto
    default_name = "General"
    row = _get_material_by_name(default_name)
    return int(row["MaterialId"]) if row else _create_material(default_name, "Material por defecto")



@bp.get("/")
@login_required
@roles_required("Administrador")
def list_products():
    rows = fetch_all("""
        SELECT ProductId, SKU, Name, Price, TaxIncluded, Active,
               CategoryId, MaterialId, WeightGrams, WidthMm, HeightMm
        FROM dbo.Products
        ORDER BY CreatedAt DESC
    """)
    return render_template("admin_products/list.html", rows=rows or [])


@bp.get("/new")
@login_required
@roles_required("Administrador")
def new_product_form():
    return render_template("admin_products/form.html",
                           item=None,
                           categories=_get_categories())


@bp.post("/new")
@login_required
@roles_required("Administrador")
def new_product_post():
    sku         = (request.form.get("sku") or "").strip()
    name        = (request.form.get("name") or "").strip()
    description = (request.form.get("description") or "").strip()

    # Categoría: viene del <select> (puede ser None si permites sin categoría)
    category_id = _to_int_or_none(request.form.get("category_id"))

    # ❌ SIN creación automática de material
    # Material: viene del <select> o vacío → None
    material_id = _to_int_or_none(request.form.get("material_id"))

    weight_g  = request.form.get("weight_grams") or None
    width_mm  = request.form.get("width_mm") or None
    height_mm = request.form.get("height_mm") or None

    price    = (request.form.get("price") or "").strip()
    tax_incl = 1 if (request.form.get("tax_included") == "on") else 0
    active   = 1 if (request.form.get("active") == "on") else 1

    if not sku or not name or not price:
        flash("SKU, Nombre y Precio son obligatorios.", "warning")
        return redirect(url_for("admin_products.new_product_form"))

    try:
        price_val = float(price)
    except ValueError:
        flash("Precio inválido.", "danger")
        return redirect(url_for("admin_products.new_product_form"))

    new_id = execute_returning_id("""
        INSERT INTO dbo.Products
            (SKU, Name, Description, CategoryId, MaterialId,
             WeightGrams, WidthMm, HeightMm,
             Price, TaxIncluded, Active, CreatedAt)
        OUTPUT INSERTED.ProductId
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, SYSUTCDATETIME());
    """, (sku, name, description,
          category_id, material_id,
          _to_num(weight_g), _to_num(width_mm), _to_num(height_mm),
          price_val, tax_incl, active))

    flash("Producto creado.", "success")
    return redirect(url_for("admin_products.list_products"))



@bp.get("/edit/<int:pid>")
@login_required
@roles_required("Administrador")
def edit_product_form(pid: int):
    item = fetch_one("""
        SELECT TOP 1 ProductId, SKU, Name, Description, CategoryId, MaterialId,
               WeightGrams, WidthMm, HeightMm, Price, TaxIncluded, Active
        FROM dbo.Products WHERE ProductId = ?
    """, (pid,))
    if not item:
        flash("Producto no encontrado.", "warning")
        return redirect(url_for("admin_products.list_products"))
    return render_template("admin_products/form.html",
                           item=item,
                           categories=_get_categories())


@bp.post("/edit/<int:pid>")
@login_required
@roles_required("Administrador")
def edit_product_post(pid: int):
    sku         = (request.form.get("sku") or "").strip()
    name        = (request.form.get("name") or "").strip()
    description = (request.form.get("description") or "").strip()

    # Categoría: del <select> (puede ser None)
    category_id = _to_int_or_none(request.form.get("category_id"))

    # ❌ SIN creación automática de material
    material_id = _to_int_or_none(request.form.get("material_id"))

    weight_g  = request.form.get("weight_grams") or None
    width_mm  = request.form.get("width_mm") or None
    height_mm = request.form.get("height_mm") or None

    price    = (request.form.get("price") or "").strip()
    tax_incl = 1 if (request.form.get("tax_included") == "on") else 0
    active   = 1 if (request.form.get("active") == "on") else 0

    if not sku or not name or not price:
        flash("SKU, Nombre y Precio son obligatorios.", "warning")
        return redirect(url_for("admin_products.edit_product_form", pid=pid))

    try:
        price_val = float(price)
    except ValueError:
        flash("Precio inválido.", "danger")
        return redirect(url_for("admin_products.edit_product_form", pid=pid))

    execute("""
        UPDATE dbo.Products
        SET SKU=?, Name=?, Description=?, CategoryId=?, MaterialId=?,
            WeightGrams=?, WidthMm=?, HeightMm=?,
            Price=?, TaxIncluded=?, Active=?, UpdatedAt=SYSUTCDATETIME()
        WHERE ProductId=?
    """, (sku, name, description,
          category_id, material_id,
          _to_num(weight_g), _to_num(width_mm), _to_num(height_mm),
          price_val, tax_incl, active, pid))

    flash("Producto actualizado.", "success")
    return redirect(url_for("admin_products.list_products"))




@bp.post("/delete/<int:pid>")
@login_required
@roles_required("Administrador")
def delete_product(pid: int):
    try:
        # 1) elimina dependencias conocidas
        execute("DELETE FROM dbo.ProductAudit WHERE ProductId = ?", (pid,))
        # Si tienes otras tablas hijas, repite aquí (OrderItems, InventoryKardex, etc.)

        # 2) elimina el producto
        execute("DELETE FROM dbo.Products WHERE ProductId = ?", (pid,))

        flash("Producto eliminado.", "info")
    except Exception as e:
        flash(f"No se pudo eliminar el producto: {e}", "danger")
    return redirect(url_for("admin_products.list_products"))


def _get_categories():
    return fetch_all("SELECT CategoryId, Name FROM dbo.Categories WHERE Active=1 ORDER BY Name")

def _to_int_or_none(v):
    v = (v or "").strip()
    return int(v) if v.isdigit() else None

def _exists_category(cid: int) -> bool:
    r = fetch_one("SELECT 1 AS ok FROM dbo.Categories WHERE CategoryId = ?", (cid,))
    return bool(r)


