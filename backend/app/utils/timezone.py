from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# Zona horaria de Lima, Perú
lima_tz = ZoneInfo("America/Lima")

def now_lima() -> datetime:
    """Devuelve la fecha y hora actuales con tz America/Lima (timezone-aware)."""
    return datetime.now(lima_tz)

def to_lima(dt: datetime) -> datetime:
    """
    Convierte un datetime a America/Lima. Si es naive, asume que está en UTC y lo convierte a Lima.
    """
    if dt.tzinfo is None:
        # Asumir UTC si es naive para evitar ambigüedades
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(lima_tz)
