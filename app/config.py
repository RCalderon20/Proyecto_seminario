import os
from dotenv import load_dotenv
load_dotenv()

def _default_driver():
    # Si no estás en Windows, por defecto usa FreeTDS (para Render/Linux)
    return "ODBC Driver 17 for SQL Server" if os.name == "nt" else "FreeTDS"

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "change-me")

    MSSQL_SERVER   = os.getenv("MSSQL_SERVER", "DAVID").strip()
    MSSQL_PORT     = int(os.getenv("MSSQL_PORT", "1433"))
    MSSQL_DATABASE = os.getenv("MSSQL_DATABASE", "JoyeríaDelCentroDB").strip()
    MSSQL_USER     = os.getenv("MSSQL_USER", "sa").strip()
    MSSQL_PASSWORD = os.getenv("MSSQL_PASSWORD", "").strip()
    MSSQL_DRIVER   = os.getenv("MSSQL_DRIVER", _default_driver()).strip()

    @property
    def ODBC_STRING(self) -> str:
        """
        Cadena ODBC para pyodbc.
        - En local (Windows): ODBC 17/18 de Microsoft → usa SERVER=host,port
        - En Render (Linux):  FreeTDS (tdsodbc) → usa SERVER=host y PORT=port
        """
        driver = self.MSSQL_DRIVER

        # ---- Rama para FreeTDS o rutas absolutas (Render/Linux) ----
        if driver.lower() in ("freetds", "tdsodbc") or driver.endswith(".so") or driver.startswith("/"):
            return (
                f"DRIVER={driver if driver.startswith('/') else '{FreeTDS}'};"
                f"SERVER={self.MSSQL_SERVER};"
                f"PORT={self.MSSQL_PORT};"
                f"DATABASE={self.MSSQL_DATABASE};"
                f"UID={self.MSSQL_USER};"
                f"PWD={self.MSSQL_PASSWORD};"
                "TDS_Version=7.4;"
                "Encrypt=Yes;"
                "TrustServerCertificate=Yes;"
                "ClientCharset=UTF-8;"
                "Connection Timeout=30;"
            )

        # ---- Rama Microsoft ODBC (Windows) ----
        return (
            f"DRIVER={{{driver}}};"
            f"SERVER={self.MSSQL_SERVER},{self.MSSQL_PORT};"
            f"DATABASE={self.MSSQL_DATABASE};"
            f"UID={self.MSSQL_USER};"
            f"PWD={self.MSSQL_PASSWORD};"
            "Encrypt=Yes;"
            "TrustServerCertificate=Yes;"
            "Connection Timeout=30;"
        )

config = Config()

# Imprime en logs el driver seleccionado (útil en Render)
print(f"[config] MSSQL_DRIVER='{config.MSSQL_DRIVER}'  (os.name={os.name})")
