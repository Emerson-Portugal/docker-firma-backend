from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.openapi.utils import get_openapi
from typing import List, Optional
import uvicorn
from pathlib import Path
import os
from datetime import datetime , timezone
from app.utils.timezone import now_lima

# Importar routers
try:
    from app.api.endpoints.auth import auth_controller, auth_valider
    from app.api.endpoints.rrhh import rrhh_subir
    from app.api.endpoints.empleados import empleados_firmar, empleados_verificar_firma
    from app.api.endpoints.soporte import soporte
except ImportError:
    # Para cuando se ejecute directamente el archivo
    from .api.endpoints.auth import auth_controller, auth_valider
    from .api.endpoints.rrhh import rrhh_subir
    from .api.endpoints.empleados import empleados_firmar, empleados_verificar_firma
    from .api.endpoints.soporte import soporte

# Crear la aplicación FastAPI
app = FastAPI(
    title="API de Sistema de Firmas",
    description="API para el sistema de firmas de usuarios de Espinar",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/api/v1/openapi.json",
    openapi_tags=[
        {
            "name": "Autenticación",
            "description": "Endpoints para autenticación y validación de usuarios"
        },
        {
            "name": "RRHH",
            "description": "Endpoints para gestión de documentos de Recursos Humanos"
        },
        {
            "name": "Empleados",
            "description": "Endpoints para que los empleados gestionen sus documentos"
        },
        {
            "name": "Salud",
            "description": "Endpoints para verificar el estado del servicio"
        },
        {
            "name": "Verificación de Firma",
            "description": "Endpoints para verificar la firma de los documentos"
        }
    ]
)

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    
    openapi_schema = get_openapi(
        title="API de Sistema de Firmas",
        version="1.0.0",
        description="API para el sistema de firmas de usuarios de Espinar",
        routes=app.routes,
    )
    
    # Configuración de autenticación en Swagger UI
    openapi_schema["components"]["securitySchemes"] = {
        "Bearer": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "Ingrese el token JWT con el prefijo 'Bearer ' (sin comillas)"
        }
    }
    
    # Asegurar que todas las rutas requieran autenticación por defecto
    for path in openapi_schema.get("paths", {}).values():
        for method in path.values():
            # Solo agregar seguridad si no es el endpoint de login
            if not (method.get("operationId") == "login" or 
                   (method.get("tags") and "Autenticación" in method["tags"] and method.get("operationId") == "login")):
                method["security"] = [{"Bearer": []}]
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En producción, reemplaza con los orígenes permitidos
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Obtener la ruta base del proyecto
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Montar directorios estáticos con rutas absolutas
app.mount(
    "/originales", 
    StaticFiles(directory=os.path.join(BASE_DIR, "storage", "originales")), 
    name="originales"
)
app.mount(
    "/firmados", 
    StaticFiles(directory=os.path.join(BASE_DIR, "storage", "firmados")), 
    name="firmados"
)

# Incluir routers
try:
    app.include_router(
        auth_controller.router,
        prefix="/api/v1/auth",
        tags=["Autenticación"]
    )
    app.include_router(
        auth_valider.router,
        prefix="/api/v1/auth",
        tags=["Autenticación"]
    )
    app.include_router(
        rrhh_subir.router,
        prefix="/api/v1/rrhh",
        tags=["RRHH"]
    )
    app.include_router(
        empleados_firmar.router,
        prefix="/api/v1",
        tags=["Empleados"]
    )
    app.include_router(
        empleados_verificar_firma.router,
        prefix="/api/v1",
        tags=["Verificación de Firma"]
    )
    app.include_router(
        soporte.router,
        prefix="/api/v1",
        tags=["Soporte"]
    )
except Exception as e:
    print(f"Error al importar routers: {e}")

# Endpoint para verificar el estado del servicio
@app.get("/health", tags=["Salud"])
async def health_check():
    """
    Verifica el estado del servicio y la conexión a la base de datos.
    
    Returns:
        dict: Estado del servicio y conexión a la base de datos
    """
    try:
        from .database import get_connection
        conn = get_connection()
        if conn:
            conn.close()
            return {
                "status": "ok",
                "database": "connected",
                "timestamp": now_lima().isoformat()

            }
        else:
            return {
                "status": "error",
                "database": "connection_failed",
                "timestamp": now_lima().isoformat()

            }
    except Exception as e:
        return {
            "status": "error",
            "database": "error",
            "error": str(e),
            "timestamp": now_lima().isoformat()

        }

# Si se ejecuta este archivo directamente
if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)