# Imagen base oficial de Python
FROM python:3.13

# Establecer directorio de trabajo
WORKDIR /app

# Configurar locales desde el inicio
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8
ENV PYTHONUNBUFFERED=1


# Instalar dependencias del sistema (opcional, para psycopg2)
RUN apt-get update && apt-get install -y build-essential libpq-dev && rm -rf /var/lib/apt/lists/*

# Copiar requirements y luego instalar
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Copiar todo el código de la app
COPY . .

# Variables de entorno por defecto (opcional)
ENV PYTHONUNBUFFERED=1

# Exponer el puerto donde correrá uvicorn
EXPOSE 8000

# Comando para iniciar la aplicación con Uvicorn sin reload (producción)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

