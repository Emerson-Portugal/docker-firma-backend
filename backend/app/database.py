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
        return conn
    except psycopg2.Error as e:
        print(f"Error de conexión: {e}")
        return None
