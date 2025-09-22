import psycopg2
from psycopg2.extras import RealDictCursor
from .config import settings

def get_connection():
    try:
        conn = psycopg2.connect(
            host=settings.DB_HOST,
            port=settings.DB_PORT,
            dbname=settings.DB_NAME,
            user=settings.DB_USER,
            password=settings.DB_PASSWORD
        )
        print("Conexión Exitosa")
        # Fijar la zona horaria de la sesión a America/Lima
        try:
            with conn.cursor() as cur:
                cur.execute("SET TIME ZONE 'America/Lima'")
        except Exception as _e:
            # No interrumpir la conexión si falla este ajuste, pero registrar
            print(f"Advertencia: no se pudo fijar timezone de sesión: {_e}")
        return conn
    except psycopg2.Error as e:
        print(f"Error de conexión: {e}")
        return None
