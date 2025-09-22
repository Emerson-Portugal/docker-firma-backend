# Imagen base oficial de Python
FROM python:3.13

# Establecer directorio de trabajo
WORKDIR /app

# Configurar locales desde el inicio
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8
ENV PYTHONUNBUFFERED=1


# Instalar dependencias del sistema (psycopg2) y tzdata para zona horaria
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y \
    build-essential \
    libpq-dev \
    tzdata \
  && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime \
  && echo $TZ > /etc/timezone \
  && rm -rf /var/lib/apt/lists/*

# Copiar requirements y luego instalar
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Copiar todo el código de la app
COPY . .

# Variables de entorno por defecto (opcional)
ENV PYTHONUNBUFFERED=1
ENV TZ=America/Lima

# Exponer el puerto donde correrá uvicorn
EXPOSE 8000

# Comando para iniciar la aplicación con Uvicorn sin reload (producción)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
