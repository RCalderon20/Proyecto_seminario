# app/blueprints/admin_dashboard.py
from flask import Blueprint, render_template, jsonify, request, send_file, abort
from utils import login_required, roles_required
from ..db import (
    dash_sales_by_month,
    dash_top_products,
    dash_user_kpis,
    dash_order_kpis,
)
import io
import pandas as pd
from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet


bp = Blueprint("admin_dashboard", __name__, url_prefix="/admin/dashboard")


@bp.get("/")
@login_required
@roles_required("Administrador")
def dashboard_page():
    """
    Renderiza la página del dashboard.
    La data pesada se pide por AJAX a /admin/dashboard/data para mantener la página rápida.
    """
    return render_template("admin_dashboard.html")


@bp.get("/data")
@login_required
@roles_required("Administrador")
def dashboard_data():
    """
    Devuelve JSON con los datasets para Chart.js
    """
    sales = dash_sales_by_month()          # [{YM:'2025-01', Total: 1234.56}, ...]
    top = dash_top_products(limit=5)       # [{Name:'Anillo ...', Qty: 42, Total: 999.00}, ...]
    users = dash_user_kpis()               # dict con totales de usuarios
    orders = dash_order_kpis()             # dict con totales / hoy

    # Normalizamos estructuras para Chart.js
    sales_labels = [r["YM"] for r in sales]
    sales_values = [float(r["Total"]) for r in sales]

    top_labels = [r["Name"] for r in top]
    top_qty = [int(r["Qty"]) for r in top]
    top_total = [float(r["Total"]) for r in top]

    return jsonify({
        "sales": {"labels": sales_labels, "values": sales_values},
        "topProducts": {"labels": top_labels, "qty": top_qty, "total": top_total},
        "userKpis": users,
        "orderKpis": orders,
    })


# Mapea nombre de dataset -> DataFrame
def _dataset_to_dataframe(name: str) -> pd.DataFrame:
    name = (name or "").strip().lower()
    if name == "users":
        k = dash_user_kpis()  # dict
        rows = [
            {"Métrica": "Usuarios totales", "Valor": k.get("totalUsers", 0)},
            {"Métrica": "Usuarios activos", "Valor": k.get("activeUsers", 0)},
            {"Métrica": "Nuevos (30 días)", "Valor": k.get("newLast30", 0)},
        ]
        return pd.DataFrame(rows)

    if name == "orders":
        k = dash_order_kpis()
        rows = [
            {"Métrica": "Pedidos hoy", "Valor": k.get("ordersToday", 0)},
            {"Métrica": "Ventas hoy (Q)", "Valor": k.get("revenueToday", 0.0)},
            {"Métrica": "Pedidos últimos 30 días", "Valor": k.get("ordersLast30", 0)},
        ]
        return pd.DataFrame(rows)

    if name == "sales_by_month":
        rows = dash_sales_by_month()  # [{YM, Total}]
        # Renombramos columnas a algo más amable
        if not rows:
            return pd.DataFrame(columns=["Mes", "Ventas (Q)"])
        return pd.DataFrame(rows).rename(columns={"YM": "Mes", "Total": "Ventas (Q)"})

    if name == "top_products":
        rows = dash_top_products(limit=20)  # puedes cambiar el límite
        if not rows:
            return pd.DataFrame(columns=["Producto", "Unidades", "Ventas (Q)"])
        return (
            pd.DataFrame(rows)
            .rename(columns={"Name": "Producto", "Qty": "Unidades", "Total": "Ventas (Q)"})
        )

    raise ValueError("dataset desconocido")

# Vista previa (JSON -> la UI pinta la tabla)
@bp.get("/report/preview")
@login_required
@roles_required("Administrador")
def report_preview():
    dataset = request.args.get("dataset")
    try:
        df = _dataset_to_dataframe(dataset)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400

    # Devolvemos columnas y filas (como strings) para una tabla simple
    cols = list(df.columns)
    rows = df.fillna("").astype(str).values.tolist()
    return jsonify({"ok": True, "columns": cols, "rows": rows})

# Descarga
@bp.get("/report/export")
@login_required
@roles_required("Administrador")
def report_export():
    dataset = request.args.get("dataset")
    fmt = (request.args.get("format") or "xlsx").lower()

    try:
        df = _dataset_to_dataframe(dataset)
    except Exception as e:
        abort(400, str(e))

    filename_base = {
        "users": "usuarios",
        "orders": "pedidos",
        "sales_by_month": "ventas_por_mes",
        "top_products": "top_productos",
    }.get(dataset, "reporte")

    if fmt == "xlsx":
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Reporte")
        output.seek(0)
        return send_file(
            output,
            as_attachment=True,
            download_name=f"{filename_base}.xlsx",
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    if fmt == "xml":
        output = io.BytesIO()
    # Fuerza el parser estándar (no requiere lxml)
        xml_str = df.to_xml(
            index=False,
            root_name="reporte",
            row_name="fila",
            parser="etree"        # <<--- clave
        )
        output.write(xml_str.encode("utf-8"))
        output.seek(0)
        return send_file(
        output,
        as_attachment=True,
        download_name=f"{filename_base}.xml",
        mimetype="application/xml",
    )

    if fmt == "pdf":
        output = io.BytesIO()
        # PDF simple con ReportLab (tabla)
        doc = SimpleDocTemplate(output, pagesize=landscape(letter), leftMargin=24, rightMargin=24, topMargin=24, bottomMargin=24)
        story = []
        styles = getSampleStyleSheet()
        title_map = {
            "users": "Usuarios (KPIs)",
            "orders": "Pedidos / Ventas (KPIs)",
            "sales_by_month": "Ventas por mes",
            "top_products": "Top de productos",
        }
        story.append(Paragraph(title_map.get(dataset, "Reporte"), styles["Title"]))
        story.append(Spacer(1, 12))

        data = [list(df.columns)] + df.fillna("").astype(str).values.tolist()
        table = Table(data, repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#eeeeee")),
            ("TEXTCOLOR", (0,0), (-1,0), colors.black),
            ("ALIGN", (0,0), (-1,-1), "CENTER"),
            ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTSIZE", (0,0), (-1,-1), 9),
            ("GRID", (0,0), (-1,-1), 0.25, colors.grey),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#fbfbfb")]),
        ]))
        story.append(table)
        doc.build(story)
        output.seek(0)
        return send_file(output, as_attachment=True, download_name=f"{filename_base}.pdf", mimetype="application/pdf")

    abort(400, "Formato no soportado (usa pdf, xlsx o xml)")