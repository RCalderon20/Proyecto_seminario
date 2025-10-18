from flask import Blueprint, render_template, request
from ..db import fetch_all
from flask import Blueprint, request, render_template
from ..db import catalog_get_categories, catalog_search_products

bp = Blueprint("catalog", __name__)

@bp.get("/")
def home():
    q = (request.args.get("q") or "").strip()
    # cat puede llegar vacío
    cat_raw = request.args.get("cat")
    cat = int(cat_raw) if cat_raw and cat_raw.isdigit() else None

    # página
    try:
        page = int(request.args.get("page", "1"))
    except ValueError:
        page = 1
    if page < 1: page = 1
    page_size = 50

    products, total = catalog_search_products(q, cat, page, page_size)
    categories = catalog_get_categories()

    # Datos para paginación
    total_pages = (total + page_size - 1) // page_size if total else 1
    pagination = {
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
        "has_prev": page > 1,
        "has_next": page < total_pages,
    }

    return render_template(
        "catalog.html",
        products=products,
        q=q,
        categories=categories,
        selected_cat=cat,
        pagination=pagination,
    )