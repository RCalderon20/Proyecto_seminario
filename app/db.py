# db.py — versión corregida para Azure SQL + pyodbc

import os
import hmac
import hashlib
from typing import Optional

import pyodbc
from .config import config
from utils import pbkdf2_hash_password, PBKDF2_ITER, PBKDF2_DKLEN

# ---------------------------------------------------------------------------
# Conexión a SQL Server (Azure-friendly)
#   - NO usar "USE <db>" (Azure retorna 40508).
#   - Conectar directamente a la base desde la cadena ODBC.
# ---------------------------------------------------------------------------

#conexion anterior
def get_connection():
   """
    Abre conexión directamente a la base definida en config.ODBC_STRING.
    """
   return pyodbc.connect(config.ODBC_STRING)

# ---------------------------------------------------------------------------
# Utilidades SQL
# ---------------------------------------------------------------------------

def fetch_all(query: str, params: tuple = ()):
    with get_connection() as con:
        cur = con.cursor()
        cur.execute(query, params)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

def fetch_one(query: str, params: tuple = ()):
    rows = fetch_all(query, params)
    return rows[0] if rows else None

def execute(query: str, params: tuple = ()):
    with get_connection() as con:
        cur = con.cursor()
        cur.execute(query, params)
        con.commit()

def execute_returning_id(sql: str, params: tuple = ()):
    with get_connection() as cn:
        cur = cn.cursor()
        cur.execute(sql, params)
        row = cur.fetchone()
        cn.commit()
    return int(row[0]) if row else None

# ---------------------------------------------------------------------------
# Stored procedure existente
# ---------------------------------------------------------------------------

def exec_sp_create_order_from_cart(cart_id: int, user_id: int) -> int:
    with get_connection() as con:
        cur = con.cursor()
        cur.execute(
            """
            DECLARE @OrderId INT;
            EXEC dbo.sp_CreateOrderFromCart @CartId=?, @UserId=?, @OrderId=@OrderId OUTPUT;
            SELECT @OrderId AS OrderId;
            """,
            (cart_id, user_id),
        )
        row = cur.fetchone()
        if not row or row[0] is None:
            raise RuntimeError("sp_CreateOrderFromCart no devolvió OrderId (NULL).")
        return int(row[0])

# ---------------------------------------------------------------------------
# Carrito
# ---------------------------------------------------------------------------

def get_or_create_cart(cart_id: int | None) -> int:
    with get_connection() as con:
        cur = con.cursor()
        if cart_id:
            cur.execute("SELECT 1 FROM dbo.Carts WHERE CartId = ?", (cart_id,))
            if cur.fetchone():
                return int(cart_id)

        # buscar carrito NULL existente
        cur.execute("SELECT TOP 1 CartId FROM dbo.Carts WHERE UserId IS NULL")
        row = cur.fetchone()
        if row:
            return int(row[0])

        # crear carrito
        cur.execute("INSERT INTO dbo.Carts (UserId) VALUES (NULL)")
        con.commit()
        cur.execute("SELECT SCOPE_IDENTITY()")
        return int(cur.fetchone()[0])

def cart_add_item(cart_id: int, product_id: int, qty: int = 1):
    if qty <= 0:
        qty = 1
    with get_connection() as con:
        cur = con.cursor()
        cur.execute("SELECT Price FROM dbo.Products WHERE ProductId = ? AND Active = 1", (product_id,))
        row = cur.fetchone()
        if not row:
            raise ValueError("Producto no existe o no está activo.")
        price = float(row[0])

        try:
            cur.execute(
                """
                INSERT INTO dbo.CartItems (CartId, ProductId, Quantity, UnitPrice)
                VALUES (?,?,?,?)
                """,
                (cart_id, product_id, qty, price),
            )
        except Exception:
            cur.execute(
                """
                UPDATE dbo.CartItems
                   SET Quantity = Quantity + ?
                 WHERE CartId = ? AND ProductId = ?
                """,
                (qty, cart_id, product_id),
            )
        con.commit()

def cart_get_items(cart_id: int):
    with get_connection() as con:
        cur = con.cursor()
        cur.execute(
            """
            SELECT ci.CartItemId, ci.ProductId, p.Name, p.SKU,
                   ci.Quantity, ci.UnitPrice, (ci.Quantity*ci.UnitPrice) AS LineTotal
              FROM dbo.CartItems ci
              JOIN dbo.Products p ON p.ProductId = ci.ProductId
             WHERE ci.CartId = ?
             ORDER BY ci.CartItemId DESC
            """,
            (cart_id,),
        )
        cols = [c[0] for c in cur.description]
        items = [dict(zip(cols, r)) for r in cur.fetchall()]
        subtotal = sum(i["LineTotal"] for i in items)
        return items, float(subtotal)

def cart_update_qty(cart_item_id: int, qty: int):
    if qty <= 0:
        cart_remove_item(cart_item_id)
        return
    with get_connection() as con:
        cur = con.cursor()
        cur.execute("UPDATE dbo.CartItems SET Quantity=? WHERE CartItemId=?", (qty, cart_item_id))
        con.commit()

def cart_remove_item(cart_item_id: int):
    with get_connection() as con:
        cur = con.cursor()
        cur.execute("DELETE FROM dbo.CartItems WHERE CartItemId=?", (cart_item_id,))
        con.commit()

def cart_clear(cart_id: int):
    with get_connection() as con:
        cur = con.cursor()
        cur.execute("DELETE FROM dbo.CartItems WHERE CartId=?", (cart_id,))
        con.commit()

# ---------------------------------------------------------------------------
# Usuarios y auth
# ---------------------------------------------------------------------------

def _hash_password(password: str, salt: bytes) -> bytes:
    # PBKDF2-HMAC-SHA256; 100k iteraciones
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)

def user_get_by_email(email: str):
    return fetch_one(
        """
        SELECT UserId, Email, FirstName, LastName, PasswordHash, PasswordSalt, IsActive
        FROM dbo.Users WHERE Email = ?
        """,
        (email,),
    )

def user_create(email: str, first: str, last: str, password: str) -> Optional[int]:
    salt = os.urandom(16)  # 128-bit
    hash_bytes = pbkdf2_hash_password(password, salt, PBKDF2_ITER, PBKDF2_DKLEN)
    sql = """
    INSERT INTO dbo.Users (Email, FirstName, LastName, PasswordHash, PasswordSalt, IsActive, CreatedAt)
    VALUES (?, ?, ?, ?, ?, 1, SYSUTCDATETIME());
    SELECT CAST(SCOPE_IDENTITY() AS INT);
    """
    with get_connection() as cn:
        cur = cn.cursor()
        cur.execute(sql, (email, first, last, hash_bytes, salt))
        row = cur.fetchone()
        cn.commit()
    return int(row[0]) if row else None

def user_update_password(user_id: int, new_password: str) -> None:
    salt = os.urandom(16)
    hash_bytes = pbkdf2_hash_password(new_password, salt, PBKDF2_ITER, PBKDF2_DKLEN)
    sql = """
    UPDATE dbo.Users
    SET PasswordHash = ?, PasswordSalt = ?, UpdatedAt = SYSUTCDATETIME()
    WHERE UserId = ?
    """
    with get_connection() as cn:
        cur = cn.cursor()
        cur.execute(sql, (hash_bytes, salt, user_id))
        cn.commit()

def user_verify_password(email: str, password: str):
    with get_connection() as con:
        cur = con.cursor()
        cur.execute(
            """
            SELECT UserId, PasswordHash, PasswordSalt, IsActive
            FROM dbo.Users WHERE Email = ?
            """,
            (email,),
        )
        r = cur.fetchone()
        if not r:
            return None
        user_id, db_hash, db_salt, is_active = r
        if not is_active:
            return None
        calc = _hash_password(password, bytes(db_salt))
        if hmac.compare_digest(calc, bytes(db_hash)):
            return int(user_id)
        return None

# ---------------------------------------------------------------------------
# Pedidos (consultas)
# ---------------------------------------------------------------------------

def orders_get_history(user_id: int):
    sql = """
    SELECT
        o.OrderId,
        o.OrderNumber,
        o.CreatedAt,
        o.Subtotal,
        o.TaxAmount,
        o.TotalAmount,
        CASE o.OrderStatusId
            WHEN 1 THEN 'Creado'
            WHEN 2 THEN 'Confirmado'
            WHEN 3 THEN 'En proceso'
            WHEN 4 THEN 'Enviado'
            WHEN 5 THEN 'Completado'
            WHEN 6 THEN 'Cancelado'
            ELSE CONCAT('Estado #', o.OrderStatusId)
        END AS StatusName
    FROM dbo.Orders o
    WHERE o.UserId = ?
    ORDER BY o.CreatedAt DESC;
    """
    return fetch_all(sql, (user_id,))

def user_orders(user_id: int):
    sql = """
    SELECT
        o.OrderId,
        o.OrderNumber,
        CONVERT(varchar(19), o.CreatedAt, 120) AS CreatedAt,   -- yyyy-mm-dd hh:mm:ss
        os.Name AS Status,
        CAST(o.Subtotal AS decimal(18,2))   AS Subtotal,
        CAST(o.TaxAmount AS decimal(18,2))  AS TaxAmount,
        CAST(COALESCE(o.TotalAmount, o.Subtotal) AS decimal(18,2)) AS Total
    FROM dbo.Orders o
    LEFT JOIN dbo.OrderStatus os ON os.OrderStatusId = o.OrderStatusId
    WHERE o.UserId = ?
    ORDER BY o.OrderId DESC;
    """
    return fetch_all(sql, (user_id,))

def user_order_header(order_id: int, user_id: int):
    sql = """
    SELECT TOP (1)
        o.OrderId,
        o.OrderNumber,
        CONVERT(varchar(19), o.CreatedAt, 120) AS CreatedAt,
        os.Name AS Status,
        CAST(o.Subtotal AS decimal(18,2))   AS Subtotal,
        CAST(o.TaxAmount AS decimal(18,2))  AS TaxAmount,
        CAST(COALESCE(o.TotalAmount, o.Subtotal) AS decimal(18,2)) AS Total
    FROM dbo.Orders o
    LEFT JOIN dbo.OrderStatus os ON os.OrderStatusId = o.OrderStatusId
    WHERE o.OrderId = ? AND o.UserId = ?;
    """
    return fetch_one(sql, (order_id, user_id))

def user_order_items(order_id: int, user_id: int):
    sql = """
    SELECT
        p.Name,
        p.SKU,
        oi.ProductId,
        oi.Quantity,
        CAST(COALESCE(oi.UnitPrice, p.Price) AS decimal(18,2)) AS UnitPrice,
        CAST((oi.Quantity * COALESCE(oi.UnitPrice, p.Price)) AS decimal(18,2)) AS LineTotal
    FROM dbo.OrderItems oi
    INNER JOIN dbo.Orders o      ON o.OrderId = oi.OrderId AND o.UserId = ?
    INNER JOIN dbo.Products p    ON p.ProductId = oi.ProductId
    WHERE oi.OrderId = ?
    ORDER BY oi.OrderItemId DESC;
    """
    return fetch_all(sql, (user_id, order_id))

# ---------------------------------------------------------------------------
# Notificaciones
# ---------------------------------------------------------------------------

def notifications_get_all(user_id: int):
    sql = """
    SELECT
        NotificationId,
        UserId,
        NotificationTypeId,
        Subject,
        MessageBody,
        RelatedEntity,
        RelatedId,
        CASE
            WHEN COL_LENGTH('dbo.Notifications','IsRead') IS NOT NULL THEN IsRead
            ELSE Sent
        END AS IsRead,
        CreatedAt
    FROM dbo.Notifications
    WHERE UserId = ?
    ORDER BY CreatedAt DESC;
    """
    return fetch_all(sql, (user_id,))

def notifications_mark_read(notification_id: int):
    execute("UPDATE dbo.Notifications SET IsRead = 1 WHERE NotificationId = ?", (notification_id,))

# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------

def get_user_roles(user_id: int):
    with get_connection() as con:
        cur = con.cursor()
        cur.execute(
            """
            SELECT r.Name
            FROM dbo.UserRoles ur
            JOIN dbo.Roles r ON r.RoleId = ur.RoleId
            WHERE ur.UserId = ?
            """,
            (user_id,),
        )
        return [row[0] for row in cur.fetchall()]

def user_get_roles(user_id: int):
    rows = fetch_all(
        """
        SELECT r.Name
        FROM dbo.UserRoles ur
        JOIN dbo.Roles r ON r.RoleId = ur.RoleId
        WHERE ur.UserId = ?
        """,
        (user_id,),
    )
    return [r["Name"] for r in rows]

# ---------------------------------------------------------------------------
# Admin: productos
# ---------------------------------------------------------------------------

def admin_products_list(q: str = ""):
    # Corregido para pyodbc: usar '?' (no variables @q)
    sql = """
    SELECT p.ProductId, p.SKU, p.Name, p.Price, p.Active, p.CreatedAt, p.UpdatedAt
    FROM dbo.Products p
    WHERE (? = '' OR p.Name LIKE '%' + ? + '%' OR p.SKU LIKE '%' + ? + '%')
    ORDER BY p.ProductId DESC;
    """
    return fetch_all(sql, (q, q, q))

def admin_product_get(product_id: int):
    sql = """
    SELECT p.*
    FROM dbo.Products p
    WHERE p.ProductId = ?
    """
    return fetch_one(sql, (product_id,))

def admin_product_create(sku, name, desc, category_id, material_id, price, tax_included, active):
    with get_connection() as con:
        cur = con.cursor()
        cur.execute(
            """
            INSERT INTO dbo.Products
              (SKU, Name, Description, CategoryId, MaterialId, Price, TaxIncluded, Active, CreatedAt)
            VALUES (?,?,?,?,?,?,?,?, SYSUTCDATETIME());
            SELECT SCOPE_IDENTITY();
            """,
            (sku, name, desc, category_id, material_id, price, tax_included, active),
        )
        return int(cur.fetchone()[0])

def admin_product_update(product_id, sku, name, desc, category_id, material_id, price, tax_included, active):
    execute(
        """
        UPDATE dbo.Products
           SET SKU=?, Name=?, Description=?, CategoryId=?, MaterialId=?, Price=?, TaxIncluded=?, Active=?,
               UpdatedAt = SYSUTCDATETIME()
         WHERE ProductId=?;
        """,
        (sku, name, desc, category_id, material_id, price, tax_included, active, product_id),
    )

def admin_product_delete(product_id: int):
    # Borrado lógico recomendado
    execute(
        """
        UPDATE dbo.Products
           SET Active = 0, UpdatedAt = SYSUTCDATETIME()
         WHERE ProductId = ?;
        """,
        (product_id,),
    )

def product_images_list(product_id: int):
    sql = """
    SELECT ImageId, ProductId, FileName, FilePath, IsPrimary, CreatedAt
    FROM dbo.ProductImages
    WHERE ProductId = ?
    ORDER BY ImageId DESC
    """
    return fetch_all(sql, (product_id,))

def product_image_add(product_id: int, filename: str, filepath: str, is_primary: int = 0):
    execute(
        """
        INSERT INTO dbo.ProductImages (ProductId, FileName, FilePath, IsPrimary, CreatedAt)
        VALUES (?,?,?,?, SYSUTCDATETIME());
        """,
        (product_id, filename, filepath, is_primary),
    )

def product_image_delete(image_id: int):
    execute("DELETE FROM dbo.ProductImages WHERE ImageId = ?;", (image_id,))

# ---------------------------------------------------------------------------
# Admin: usuarios
# ---------------------------------------------------------------------------

def roles_get_all():
    return fetch_all(
        """
        SELECT RoleId, Name, Description
        FROM dbo.Roles
        ORDER BY RoleId
        """
    )

def admin_users_list(q: str = ""):
    with get_connection() as con:
        cur = con.cursor()
        cur.execute(
            """
            SELECT
              u.UserId, u.Email, u.FirstName, u.LastName, u.IsActive,
              CONVERT(varchar(19), u.CreatedAt, 120) AS CreatedAt,
              STUFF((
                 SELECT ', ' + r2.Name
                   FROM dbo.UserRoles ur2
                   JOIN dbo.Roles r2 ON r2.RoleId = ur2.RoleId
                  WHERE ur2.UserId = u.UserId
                  FOR XML PATH(''), TYPE
              ).value('.','nvarchar(max)'), 1, 2, '') AS Roles
            FROM dbo.Users u
            WHERE (? = '' OR u.Email LIKE '%' + ? + '%' OR u.FirstName LIKE '%' + ? + '%' OR u.LastName LIKE '%' + ? + '%')
            ORDER BY u.UserId DESC;
            """,
            (q, q, q, q),
        )
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

def admin_user_get(user_id: int):
    user = fetch_one(
        """
        SELECT TOP 1 UserId, Email, FirstName, LastName, IsActive,
               CONVERT(varchar(19), CreatedAt, 120) AS CreatedAt,
               CONVERT(varchar(19), UpdatedAt, 120) AS UpdatedAt
        FROM dbo.Users WHERE UserId = ?
        """,
        (user_id,),
    )
    roles = fetch_all("SELECT RoleId FROM dbo.UserRoles WHERE UserId = ?", (user_id,))
    role_ids = [r["RoleId"] for r in roles]
    return user, role_ids

def admin_user_create(email: str, first: str, last: str, is_active: int, password: str, role_ids: list[int]) -> int:
    salt = os.urandom(16)
    hash_bytes = pbkdf2_hash_password(password, salt, PBKDF2_ITER, PBKDF2_DKLEN)

    with get_connection() as cn:
        cur = cn.cursor()

        # Garantizar que no exista el email
        cur.execute("SELECT 1 FROM dbo.Users WHERE LOWER(Email) = LOWER(?)", (email,))
        if cur.fetchone():
            raise ValueError("El correo ya está registrado.")

        # Insert usuario
        cur.execute(
            """
            INSERT INTO dbo.Users (Email, FirstName, LastName, PasswordHash, PasswordSalt, IsActive, CreatedAt)
            VALUES (?, ?, ?, ?, ?, ?, SYSUTCDATETIME());
            SELECT CAST(SCOPE_IDENTITY() AS INT);
            """,
            (email, first, last, hash_bytes, salt, is_active),
        )
        user_id = int(cur.fetchone()[0])

        # Roles
        for rid in role_ids:
            cur.execute(
                "INSERT INTO dbo.UserRoles (UserId, RoleId, CreatedAt) VALUES (?, ?, SYSUTCDATETIME())",
                (user_id, rid),
            )

        cn.commit()
    return user_id

def admin_user_update(user_id: int, email: str, first: str, last: str, is_active: int, role_ids: list[int]):
    with get_connection() as cn:
        cur = cn.cursor()
        # Validar email duplicado (de otro usuario)
        cur.execute("SELECT 1 FROM dbo.Users WHERE LOWER(Email)=LOWER(?) AND UserId<>?", (email, user_id))
        if cur.fetchone():
            raise ValueError("El correo ya está siendo usado por otro usuario.")

        cur.execute(
            """
            UPDATE dbo.Users
               SET Email = ?, FirstName = ?, LastName = ?, IsActive = ?, UpdatedAt = SYSUTCDATETIME()
             WHERE UserId = ?
            """,
            (email, first, last, is_active, user_id),
        )

        # Reemplazar roles
        cur.execute("DELETE FROM dbo.UserRoles WHERE UserId = ?", (user_id,))
        for rid in role_ids:
            cur.execute(
                "INSERT INTO dbo.UserRoles (UserId, RoleId, CreatedAt) VALUES (?, ?, SYSUTCDATETIME())",
                (user_id, rid),
            )

        cn.commit()

def admin_user_set_active(user_id: int, active: int):
    execute(
        "UPDATE dbo.Users SET IsActive = ?, UpdatedAt = SYSUTCDATETIME() WHERE UserId = ?",
        (active, user_id),
    )

def admin_user_reset_password(user_id: int, new_password: str):
    salt = os.urandom(16)
    hash_bytes = pbkdf2_hash_password(new_password, salt, PBKDF2_ITER, PBKDF2_DKLEN)
    execute(
        """
        UPDATE dbo.Users
           SET PasswordHash = ?, PasswordSalt = ?, UpdatedAt = SYSUTCDATETIME()
         WHERE UserId = ?
        """,
        (hash_bytes, salt, user_id),
    )

def admin_user_delete(user_id: int):
    execute(
        """
        UPDATE dbo.Users
           SET IsActive = 0, UpdatedAt = SYSUTCDATETIME()
         WHERE UserId = ?
        """,
        (user_id,),
    )

def admin_user_hard_delete(user_id: int):
    with get_connection() as cn:
        cur = cn.cursor()

        # Protecciones
        cur.execute("SELECT 1 FROM dbo.Orders WHERE UserId = ?", (user_id,))
        if cur.fetchone():
            raise RuntimeError("No se puede eliminar: el usuario tiene pedidos registrados.")

        # Dependencias no críticas
        cur.execute("DELETE FROM dbo.Notifications WHERE UserId = ?", (user_id,))
        cur.execute("DELETE FROM dbo.UserRoles WHERE UserId = ?", (user_id,))
        cur.execute("DELETE FROM dbo.CartItems WHERE CartId IN (SELECT CartId FROM dbo.Carts WHERE UserId = ?)", (user_id,))
        cur.execute("DELETE FROM dbo.Carts WHERE UserId = ?", (user_id,))

        # Usuario
        cur.execute("DELETE FROM dbo.Users WHERE UserId = ?", (user_id,))
        cn.commit()

def admin_user_create_with_roles(email: str, first: str, last: str, password: str, active: bool, role_ids: list[int]) -> int:
    salt = os.urandom(16)
    hash_bytes = pbkdf2_hash_password(password, salt, PBKDF2_ITER, PBKDF2_DKLEN)

    sql_insert = """
        INSERT INTO dbo.Users (Email, FirstName, LastName, PasswordHash, PasswordSalt, IsActive, CreatedAt)
        OUTPUT INSERTED.UserId
        VALUES (?, ?, ?, ?, ?, ?, SYSUTCDATETIME());
    """

    with get_connection() as cn:
        cur = cn.cursor()

        cur.execute(sql_insert, (email, first, last, hash_bytes, salt, 1 if active else 0))
        row = cur.fetchone()
        if not row:
            raise RuntimeError("No se pudo obtener el UserId al crear el usuario.")
        user_id = int(row[0])

        cur.execute("DELETE FROM dbo.UserRoles WHERE UserId = ?", (user_id,))
        if role_ids:
            for rid in role_ids:
                cur.execute(
                    "INSERT INTO dbo.UserRoles (UserId, RoleId, CreatedAt) VALUES (?, ?, SYSUTCDATETIME())",
                    (user_id, int(rid)),
                )

        cn.commit()
    return user_id

# ---------------------------------------------------------------------------
# Catálogo
# ---------------------------------------------------------------------------

def catalog_get_categories():
    sql = """
    SELECT CategoryId, Name
    FROM dbo.Categories
    WHERE Active = 1
    ORDER BY Name;
    """
    return fetch_all(sql, ())

def catalog_search_products(q: str | None, category_id: int | None,
                            page: int = 1, page_size: int = 50):
    if page < 1:
        page = 1
    if page_size < 1:
        page_size = 50

    offset = (page - 1) * page_size

    q = (q or "").strip()
    has_q = 1 if q else 0

    cat = int(category_id) if category_id else None
    has_cat = 1 if cat else 0

    # Conteo total
    count_sql = """
    SELECT COUNT(*)
      FROM dbo.Products p
      LEFT JOIN dbo.Categories c ON c.CategoryId = p.CategoryId
     WHERE p.Active = 1
       AND (? = 0 OR (p.Name LIKE '%' + ? + '%' OR p.SKU LIKE '%' + ? + '%'))
       AND (? = 0 OR p.CategoryId = ?);
    """
    with get_connection() as con:
        cur = con.cursor()
        cur.execute(count_sql, (has_q, q, q, has_cat, cat))
        total = int(cur.fetchone()[0])

        # Página de resultados
        list_sql = """
        SELECT p.ProductId, p.SKU, p.Name, p.Price,
               c.Name AS Category, p.MaterialId, p.Description
          FROM dbo.Products p
          LEFT JOIN dbo.Categories c ON c.CategoryId = p.CategoryId
         WHERE p.Active = 1
           AND (? = 0 OR (p.Name LIKE '%' + ? + '%' OR p.SKU LIKE '%' + ? + '%'))
           AND (? = 0 OR p.CategoryId = ?)
         ORDER BY p.ProductId DESC
         OFFSET ? ROWS FETCH NEXT ? ROWS ONLY;
        """
        cur.execute(list_sql, (has_q, q, q, has_cat, cat, offset, page_size))
        cols = [c[0] for c in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]

    return rows, total

# ---------------------------------------------------------------------------
# Dashboard KPIs y métricas
# ---------------------------------------------------------------------------

def dash_sales_by_month():
    """
    Ventas (TotalAmount o Subtotal) por mes de los últimos 12 meses.
    Retorna: [{YM:'2025-01', Total: 1234.56}, ...] ordenado ascendente.
    """
    sql = """
    DECLARE @start DATE = DATEADD(MONTH, -11, DATEFROMPARTS(YEAR(SYSUTCDATETIME()), MONTH(SYSUTCDATETIME()), 1));
    SELECT
        FORMAT(o.CreatedAt, 'yyyy-MM') AS YM,
        CAST(SUM(COALESCE(o.TotalAmount, o.Subtotal)) AS decimal(18,2)) AS Total
    FROM dbo.Orders o
    WHERE o.CreatedAt >= @start
      AND o.OrderStatusId IS NOT NULL
    GROUP BY FORMAT(o.CreatedAt, 'yyyy-MM')
    ORDER BY YM;
    """
    return fetch_all(sql)


def dash_top_products(limit: int = 5):
    """
    Top N productos más vendidos en los últimos 12 meses.
    Retorna: [{Name:'', Qty: 0, Total: 0.0}, ...]
    """
    sql = """
    DECLARE @start DATETIME2 = DATEADD(MONTH, -12, SYSUTCDATETIME());
    SELECT TOP (?)
        p.Name,
        SUM(oi.Quantity) AS Qty,
        CAST(SUM(oi.Quantity * COALESCE(oi.UnitPrice, p.Price)) AS decimal(18,2)) AS Total
    FROM dbo.OrderItems oi
    JOIN dbo.Orders o   ON o.OrderId = oi.OrderId
    JOIN dbo.Products p ON p.ProductId = oi.ProductId
    WHERE o.CreatedAt >= @start
    GROUP BY p.Name
    ORDER BY Qty DESC, Total DESC;
    """
    return fetch_all(sql, (limit,))


def dash_user_kpis():
    """
    KPIs de usuarios: totales, activos, nuevos 30 días.
    """
    sql = """
    SELECT
        (SELECT COUNT(*) FROM dbo.Users)                                           AS TotalUsers,
        (SELECT COUNT(*) FROM dbo.Users WHERE IsActive = 1)                        AS ActiveUsers,
        (SELECT COUNT(*) FROM dbo.Users WHERE CreatedAt >= DATEADD(DAY,-30,SYSUTCDATETIME())) AS NewLast30
    """
    row = fetch_one(sql) or {}
    return {
        "totalUsers": int(row.get("TotalUsers", 0)),
        "activeUsers": int(row.get("ActiveUsers", 0)),
        "newLast30": int(row.get("NewLast30", 0)),
    }


def dash_order_kpis():
    """
    KPIs de pedidos: pedidos de hoy, ventas de hoy, total pedidos últimos 30 días.
    """
    sql = """
    SELECT
      (SELECT COUNT(*) FROM dbo.Orders
         WHERE CONVERT(date, CreatedAt AT TIME ZONE 'UTC') = CONVERT(date, SYSUTCDATETIME() AT TIME ZONE 'UTC')) AS OrdersToday,
      (SELECT CAST(SUM(COALESCE(TotalAmount, Subtotal)) AS decimal(18,2))
         FROM dbo.Orders
         WHERE CONVERT(date, CreatedAt AT TIME ZONE 'UTC') = CONVERT(date, SYSUTCDATETIME() AT TIME ZONE 'UTC'))          AS RevenueToday,
      (SELECT COUNT(*) FROM dbo.Orders WHERE CreatedAt >= DATEADD(DAY,-30,SYSUTCDATETIME()))                                 AS OrdersLast30
    """
    row = fetch_one(sql) or {}
    return {
        "ordersToday": int(row.get("OrdersToday", 0)),
        "revenueToday": float(row.get("RevenueToday") or 0.0),
        "ordersLast30": int(row.get("OrdersLast30", 0)),
    }
