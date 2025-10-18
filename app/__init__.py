import os
from flask import Flask
from .config import config

# Blueprints principales
from .blueprints.health import bp as health_bp
from .blueprints.catalog import bp as catalog_bp
from .blueprints.orders import bp as orders_bp
from .blueprints.cart import bp as cart_bp
from .blueprints.auth import bp as auth_bp
from .blueprints.notifications import bp as notifications_bp
from .blueprints.admin_products import bp as admin_products_bp
from .blueprints.admin_dashboard import bp as admin_dashboard_bp
from .blueprints.admin_users import bp as admin_users_bp



def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = config.SECRET_KEY


      # === Config de uploads (imágenes de productos) ===
    base_dir = os.path.abspath(os.path.dirname(__file__))
    # /.../app/uploads/products (queda fuera de templates/static)
    upload_root = os.path.join(os.path.dirname(base_dir), "uploads")
    os.makedirs(os.path.join(upload_root, "products"), exist_ok=True)
    app.config["UPLOAD_ROOT"] = upload_root
    app.config["PRODUCT_UPLOAD_DIR"] = os.path.join(upload_root, "products")
    app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10MB por archivo

    # ===============================
    #   Registro de Blueprints
    # ===============================
    app.register_blueprint(health_bp)     # Comprobación de estado del sistema
    app.register_blueprint(catalog_bp)    # Catálogo de productos
    app.register_blueprint(orders_bp)     # Pedidos, checkout y mis pedidos
    app.register_blueprint(cart_bp)       # Carrito de compras
    app.register_blueprint(auth_bp)       # Autenticación (login / registro)
    app.register_blueprint(notifications_bp)  # Notificaciones
    app.register_blueprint(admin_products_bp)
    app.register_blueprint(admin_dashboard_bp)
    app.register_blueprint(admin_users_bp)

    # ===============================
    #   Configuración de Jinja2
    # ===============================
    app.jinja_env.trim_blocks = True
    app.jinja_env.lstrip_blocks = True

    # ===============================
    #   Retorno de la aplicación
    # ===============================
    return app
