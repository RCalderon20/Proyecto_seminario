# app/blueprints/health.py
from flask import Blueprint, jsonify
import pyodbc
from ..config import config
from ..db import fetch_one

bp = Blueprint("health", __name__, url_prefix="/health")

@bp.get("/")
def health():
    return jsonify({"status": "ok"})

@bp.get("/db")
def health_db():
    row = fetch_one("SELECT DB_NAME() AS CurrentDB;")
    return jsonify({"status": "ok", "db": row["CurrentDB"] if row else None})

@bp.get("/odbc")
def odbc_info():
    return jsonify({
        "installed_drivers": pyodbc.drivers(),
        "server_env": config.MSSQL_SERVER,
        "port_env": config.MSSQL_PORT
    })
