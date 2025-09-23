from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# Intentar cargar la zona horaria de Lima, Perú
try:
    lima_tz = ZoneInfo("America/Lima")
except ZoneInfoNotFoundError:
    # Fallback: offset fijo -05:00 (sin DST) si no hay base de datos IANA disponible
    print("Advertencia: No se encontró 'America/Lima' en zoneinfo. Usando offset fijo -05:00. Instala el paquete 'tzdata' en tu entorno para soporte completo.")
    lima_tz = timezone(timedelta(hours=-5))


def now_lima() -> datetime:
    """Devuelve la fecha y hora actuales con tz America/Lima (o -05:00 si no está disponible)."""
    return datetime.now(lima_tz)


def to_lima(dt: datetime) -> datetime:
    """
    Convierte un datetime a America/Lima. Si es naive, asume que está en UTC y lo convierte a Lima.
    """
    if dt.tzinfo is None:
        # Asumir UTC si es naive para evitar ambigüedades
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(lima_tz)
