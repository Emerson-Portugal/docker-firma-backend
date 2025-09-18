from fastapi import APIRouter, HTTPException, status, Depends, Request, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Dict, Any, Optional
from pydantic import BaseModel
import os
from datetime import datetime
from psycopg2.extras import RealDictCursor

from app.database import get_connection
from app.api.endpoints.auth.auth_controller import get_current_user
from app.api.endpoints.auth.auth_valider import TokenData

# Configurar el esquema de autenticación
security = HTTPBearer()

router = APIRouter(
    prefix="/empleado",
    tags=["Verificación de Firma"],
    dependencies=[Security(security)]
)

# Modelo para la respuesta de verificación de firma
class VerificacionFirmaResponse(BaseModel):
    puede_firmar: bool
    mensaje: str
    documento_pendiente: Optional[Dict[str, Any]] = None

@router.get(
    "/verificar-firma/{documento_id}",
    response_model=VerificacionFirmaResponse,
    responses={
        200: {"description": "Verificación de estado de firma exitosa"},
        401: {"description": "No autorizado - Token inválido o expirado"},
        403: {"description": "No tiene permiso para acceder a este recurso"},
        404: {"description": "Documento no encontrado"},
        500: {"description": "Error interno del servidor"}
    }
)
async def verificar_estado_firma(
    documento_id: int,
    request: Request,
    credentials: HTTPAuthorizationCredentials = Security(security),
    current_user: TokenData = Depends(get_current_user)
):
    """
    Verifica si un documento puede ser firmado verificando si hay documentos anteriores sin firmar.
    
    Retorna un objeto con:
    - puede_firmar: booleano que indica si se puede firmar el documento
    - mensaje: descripción del estado actual
    - documento_pendiente: información del documento pendiente de firma (si aplica)
    """
    # Obtener conexión a la base de datos
    conn = get_connection()
    if not conn:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error de conexión a la base de datos"
        )
    
    cursor = None
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # 1. Validar el documento
        cursor.execute("""
            SELECT d.*, u.nombre, u.dni, d.subido_en
            FROM documentos d
            JOIN usuarios u ON d.usuario_id = u.id
            WHERE d.id = %s AND d.usuario_id = %s
        """, (documento_id, current_user.id))
        
        documento = cursor.fetchone()
        
        if not documento:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Documento no encontrado o no tiene permiso para acceder a él"
            )
            
        if documento.get('estado') == 'firmado':
            return VerificacionFirmaResponse(
                puede_firmar=False,
                mensaje="El documento ya ha sido firmado previamente"
            )
        
        # Verificar si hay documentos de meses anteriores sin firmar
        if documento.get('subido_en'):
            cursor.execute("""
                SELECT id, nombre_archivo, subido_en
                FROM documentos 
                WHERE usuario_id = %s 
                AND estado != 'firmado'
                AND subido_en < %s
                AND id != %s  -- Excluir el documento actual
                ORDER BY subido_en ASC
                LIMIT 1
            """, (current_user.id, documento['subido_en'], documento_id))
            
            documento_anterior = cursor.fetchone()
            
            if documento_anterior:
                # Formatear la fecha para mostrar al usuario
                fecha_formateada = documento_anterior['subido_en'].strftime('%d/%m/%Y')
                return VerificacionFirmaResponse(
                    puede_firmar=False,
                    mensaje="Tiene un documento anterior sin firmar. Debe firmar los documentos en orden cronológico.",
                    documento_pendiente={
                        "id": documento_anterior['id'],
                        "nombre": documento_anterior['nombre_archivo'],
                        "fecha": fecha_formateada
                    }
                )
        
        # Si llegamos aquí, no hay documentos pendientes y se puede firmar
        return VerificacionFirmaResponse(
            puede_firmar=True,
            mensaje="Puede proceder con la firma del documento"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al verificar el estado de firma: {str(e)}"
        )
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
