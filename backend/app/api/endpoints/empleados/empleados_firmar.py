from fastapi import APIRouter, HTTPException, status, Depends, Request, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import os
from datetime import datetime
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from io import BytesIO
import json
from psycopg2.extras import RealDictCursor

from app.database import get_connection
from app.api.endpoints.auth.auth_controller import get_current_user
from app.api.endpoints.auth.auth_valider import TokenData
from app.utils.timezone import now_lima

# Configurar el esquema de autenticación
security = HTTPBearer()

router = APIRouter(
    prefix="/empleado",
    tags=["Empleados"],
    dependencies=[Security(security)]
)

def get_base_storage_path():
    """Obtiene la ruta base de almacenamiento"""
    return os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "storage")

def firmar_pdf(original_path, nombre_firmante, dni_firmante):
    """Agrega la firma al PDF y lo guarda en la carpeta de firmados
    Posiciona la firma en el recuadro de 'TRABAJADOR' (lado derecho inferior)."""
    # Leer el PDF original primero para conocer el tamaño de página
    reader = PdfReader(original_path)
    writer = PdfWriter()

    # Usar tamaño de la primera página como referencia
    first_page = reader.pages[0]
    page_width = float(first_page.mediabox.width)
    page_height = float(first_page.mediabox.height)

    # Crear el PDF de la firma con el mismo tamaño que el original
    packet = BytesIO()
    can = canvas.Canvas(packet, pagesize=(page_width, page_height))

    # Configurar el texto de la firma
    texto_firma_lineas = [
        "Firmado por:",
        f"{nombre_firmante}",
        f"(DNI: {dni_firmante})",
        f"Fecha: {now_lima().strftime('%d/%m/%Y %H:%M:%S')}"
    ]

    # Estilo de texto (más pequeño)
    font_size = 8
    can.setFont("Helvetica", font_size)

    # Calcular área exacta del recuadro "TRABAJADOR"
    margen = 36
    x_inicio = page_width * 0.68  # Ajustado al bloque TRABAJADOR
    x_fin = page_width - margen
    ancho_bloque = x_fin - x_inicio

    # Altura desde abajo donde va la firma
    y_firma = 650  # Ajusta si quieres más arriba o abajo

    # Calcular ancho máximo del texto para centrarlo en el bloque
    line_widths = [can.stringWidth(linea, "Helvetica", font_size) for linea in texto_firma_lineas]
    max_line_width = max(line_widths)
    x_texto = x_inicio + max(0, (ancho_bloque - max_line_width) / 2)

    # Dibujar las líneas de texto una encima de la otra, centradas
    # No dibujar fondo para no tapar líneas del PDF
    leading = 11  # separación entre líneas acorde al tamaño 8
    y_actual = y_firma + leading  # primera línea un poco arriba
    for linea in texto_firma_lineas:
        can.drawString(x_texto, y_actual, linea)
        y_actual -= leading

    can.save()
    packet.seek(0)
    overlay = PdfReader(packet).pages[0]

    # Agregar la firma solo en la última página
    total_pages = len(reader.pages)
    for i, page in enumerate(reader.pages):
        if i == total_pages - 1:
            page.merge_page(overlay)
        writer.add_page(page)

    # Crear directorio de firmados con el DNI si no existe
    firmados_dir = os.path.join(get_base_storage_path(), "firmados", dni_firmante)
    os.makedirs(firmados_dir, exist_ok=True)

    # Generar ruta del archivo firmado
    nombre_archivo = os.path.basename(original_path)
    ruta_firmado = os.path.join(firmados_dir, nombre_archivo)

    # Guardar el PDF firmado
    with open(ruta_firmado, "wb") as output_file:
        writer.write(output_file)

    # Retornar la ruta relativa al directorio de firmados
    return os.path.join("firmados", dni_firmante, nombre_archivo)

@router.post(
    "/firmar/{documento_id}",
    responses={
        200: {"description": "Documento firmado exitosamente"},
        401: {"description": "No autorizado - Token inválido o expirado"},
        403: {"description": "No tiene permiso para acceder a este recurso"},
        404: {"description": "Documento no encontrado"},
        400: {"description": "El documento ya ha sido firmado"}
    }
)
async def firmar_documento(
    documento_id: int,
    request: Request,
    credentials: HTTPAuthorizationCredentials = Security(security),
    current_user: TokenData = Depends(get_current_user)
):
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
            FOR UPDATE  -- Bloquear el registro para evitar condiciones de carrera
        """, (documento_id, current_user.id))
        
        documento = cursor.fetchone()
        
        if not documento:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Documento no encontrado o no tiene permiso para firmarlo"
            )
            
        if documento.get('estado') == 'firmado':
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El documento ya ha sido firmado previamente"
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
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "error": "documento_anterior_sin_firmar",
                        "mensaje": "No puede firmar este documento. Tiene un documento anterior sin firmar.",
                        "documento_anterior": {
                            "id": documento_anterior['id'],
                            "nombre": documento_anterior['nombre_archivo'],
                            "fecha": fecha_formateada
                        }
                    }
                )
        
        # 2. Firmar el PDF
        ruta_original = os.path.join(get_base_storage_path(), documento['ruta'])
        if not os.path.exists(ruta_original):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No se encontró el archivo original del documento"
            )
        
        # 3. Generar la ruta del archivo firmado
        ruta_firmado = firmar_pdf(
            ruta_original,
            documento['nombre'],
            documento['dni']
        )
        
        # 4. Actualizar la base de datos
        now = now_lima()
        
        # Actualizar el documento
        cursor.execute("""
            UPDATE documentos 
            SET estado = 'firmado', 
                firmado_en = %s,
                ruta = %s
            WHERE id = %s
            RETURNING *
        """, (
            now,
            ruta_firmado,
            documento_id
        ))
        
        # Obtener el documento actualizado
        documento_actualizado = cursor.fetchone()
        
        # Registrar en la tabla de firmas
        cursor.execute("""
            INSERT INTO firmas 
            (documento_id, usuario_id, ip_origen, metodo, observacion)
            VALUES (%s, %s, %s, 'app', %s)
        """, (
            documento_id,
            current_user.id,
            request.client.host if request.client else None,
            now
        ))
        
        conn.commit()
        
        # Convertir fechas a string
        if documento_actualizado.get('subido_en'):
            documento_actualizado['subido_en'] = documento_actualizado['subido_en'].isoformat()
        if documento_actualizado.get('firmado_en'):
            documento_actualizado['firmado_en'] = documento_actualizado['firmado_en'].isoformat()
        
        return {
            "message": "Documento firmado exitosamente",
            "documento": documento_actualizado
        }
        
    except HTTPException:
        if conn:
            conn.rollback()
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al firmar el documento: {str(e)}"
        )
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@router.get(
    "/mis-documentos",
    responses={
        200: {"description": "Lista de documentos del usuario autenticado o mensaje si no hay documentos"},
        500: {"description": "Error al obtener documentos"}
    }
)
async def listar_mis_documentos(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Security(security),
    current_user: TokenData = Depends(get_current_user)
):
    """
    Endpoint para que un empleado vea todos sus documentos.
    Los usuarios con rol 'rrhh' también pueden usar este endpoint para ver sus propios documentos.
    """
    conn = get_connection()
    if not conn:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error de conexión a la base de datos"
        )

    cursor = None
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Obtener los documentos del usuario autenticado
        cursor.execute("""
            SELECT d.id, d.nombre_archivo, d.ruta, d.estado, 
                   d.subido_en, d.firmado_en, u.nombre as nombre_usuario
            FROM documentos d
            JOIN usuarios u ON d.usuario_id = u.id
            WHERE u.id = %s
            ORDER BY d.subido_en DESC
        """, (current_user.id,))
        
        documentos = cursor.fetchall()
        
        if not documentos:
            return {
                "message": "No tienes documentos cargados actualmente",
                "documentos": [],
                "usuario_actual": {
                    "id": current_user.id,
                    "nombre": current_user.nombre,
                    "dni": current_user.dni,
                    "rol": current_user.rol
                }
            }
        
        # Convertir fechas a string
        for doc in documentos:
            if doc.get('subido_en'):
                doc['subido_en'] = doc['subido_en'].isoformat()
            if doc.get('firmado_en'):
                doc['firmado_en'] = doc['firmado_en'].isoformat()
        
        return {
            "message": f"Tienes {len(documentos)} documento(s)",
            "documentos": documentos,
            "usuario_actual": {
                "id": current_user.id,
                "nombre": current_user.nombre,
                "dni": current_user.dni,
                "rol": current_user.rol
            }
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener documentos: {str(e)}"
        )
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@router.get(
    "/mis-documentos/estado/{estado}",
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Lista de documentos del usuario autenticado filtrados por estado"},
        400: {"description": "Estado no válido"},
        500: {"description": "Error al obtener los documentos"}
    }
)
async def listar_mis_documentos_por_estado(
    estado: str,
    request: Request,
    credentials: HTTPAuthorizationCredentials = Security(security),
    current_user: TokenData = Depends(get_current_user)
):
    """
    Endpoint para que un empleado vea sus documentos filtrados por estado.
    
    Args:
        estado: Estado por el que filtrar ('pendiente' o 'firmado')
    """
    # Validar que el estado sea válido
    estado = estado.lower()
    if estado not in ["pendiente", "firmado"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El estado debe ser 'pendiente' o 'firmado'"
        )

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
        
        # Consulta para obtener los documentos del usuario autenticado filtrados por estado
        cursor.execute("""
            SELECT 
                d.id,
                d.nombre_archivo,
                d.ruta,
                d.estado,
                d.subido_en,
                d.firmado_en,
                u.id as usuario_id,
                u.nombre as nombre_usuario,
                u.dni as usuario_dni
            FROM 
                documentos d
            JOIN 
                usuarios u ON d.usuario_id = u.id
            WHERE 
                u.dni = %s
                AND d.estado = %s
            ORDER BY 
                d.subido_en DESC
        """, (current_user.dni, estado))
        
        documentos = cursor.fetchall()
        
        # Construir la URL base para las descargas
        base_url = str(request.base_url)
        if base_url.endswith('/'):
            base_url = base_url[:-1]
        if base_url.endswith('/docs'):
            base_url = base_url[:-5]
        
        # Procesar los resultados
        documentos_lista = []
        for doc in documentos:
            ruta_descarga = f"{base_url}/static/{doc['ruta']}"
            
            documentos_lista.append({
                "id": doc["id"],
                "nombre_archivo": doc["nombre_archivo"],
                "ruta": doc["ruta"],
                "url_descarga": ruta_descarga,
                "estado": doc["estado"],
                "subido_en": doc["subido_en"].isoformat() if doc["subido_en"] else None,
                "firmado_en": doc["firmado_en"].isoformat() if doc["firmado_en"] else None,
                "usuario": {
                    "id": doc["usuario_id"],
                    "nombre": doc["nombre_usuario"],
                    "dni": doc["usuario_dni"]
                }
            })
        
        return {
            "estado": estado,
            "total_documentos": len(documentos_lista),
            "documentos": documentos_lista
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener los documentos: {str(e)}"
        )
        
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()