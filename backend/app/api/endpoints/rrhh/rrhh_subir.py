from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, status, Request, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import os
import shutil
from datetime import datetime
import uuid
from psycopg2.extras import RealDictCursor

from app.database import get_connection
from app.api.endpoints.auth.auth_controller import get_current_user
from app.api.endpoints.auth.auth_valider import TokenData

# Configurar el esquema de autenticación
security = HTTPBearer()

router = APIRouter(
    prefix="/rrhh",
    tags=["RRHH"],
    responses={
        401: {"description": "No autorizado - Token inválido o expirado"},
        403: {"description": "No tiene permiso para acceder a este recurso"},
        500: {"description": "Error interno del servidor"}
    },
    dependencies=[Security(security)]
)

# Configuración de rutas
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
STORAGE_PATH = os.path.join(BASE_DIR, "storage", "originales")
os.makedirs(STORAGE_PATH, exist_ok=True)

ALLOWED_EXTENSIONS = {"pdf"}

def allowed_file(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@router.post(
    "/documentos/upload",
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {"description": "Documento subido exitosamente"},
        400: {"description": "Formato de archivo no válido"},
        404: {"description": "Usuario no encontrado"},
        500: {"description": "Error al procesar el documento"}
    }
)
async def upload_documento(
    request: Request,
    dni: str = Form(..., description="DNI del empleado dueño del documento"),
    file: UploadFile = File(..., description="Archivo PDF a subir"),
    credentials: HTTPAuthorizationCredentials = Security(security),
    current_user: TokenData = Depends(get_current_user)
):
    # Verificar si el usuario tiene permiso de RRHH
    if current_user.rol != "rrhh":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tiene permiso para realizar esta acción"
        )

    # Validar que el archivo sea PDF
    if not file.filename or not allowed_file(file.filename):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Solo se permiten archivos PDF"
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
        cursor = conn.cursor()
        
        # Verificar si el usuario existe y obtener su ID
        cursor.execute("SELECT id FROM usuarios WHERE dni = %s", (dni,))
        usuario = cursor.fetchone()
        if not usuario:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No se encontró el usuario con DNI {dni}"
            )
            
        usuario_id = usuario[0]

        # Verificar si ya existe un documento para este usuario en el mismo mes y año
        now = datetime.now()
        cursor.execute("""
            SELECT COUNT(*) 
            FROM documentos d
            JOIN usuarios u ON d.usuario_id = u.id
            WHERE u.dni = %s 
            AND EXTRACT(MONTH FROM d.subido_en) = %s 
            AND EXTRACT(YEAR FROM d.subido_en) = %s
        """, (dni, now.month, now.year))
        
        if cursor.fetchone()[0] > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Ya existe un documento para el usuario con DNI {dni} en {now.strftime('%B')} de {now.year}"
            )
        
        # Generar nombre del archivo con el formato DNI_Boleta_MES_ANO.pdf
        # Diccionario de meses en español
        meses = {
            1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril",
            5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto",
            9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"
        }
        mes = meses[now.month]
        ano = now.strftime("%Y")
        file_extension = os.path.splitext(file.filename)[1].lower()
        
        # Nombre del archivo
        unique_filename = f"{dni}_Boleta_{mes}_{ano}{file_extension}"
        
        # Crear directorio para el usuario si no existe (usando DNI como nombre de carpeta)
        user_dir = os.path.join(STORAGE_PATH, dni)
        os.makedirs(user_dir, exist_ok=True)
        
        # Ruta relativa para guardar en la BD (sin el STORAGE_PATH base)
        relative_path = os.path.join("originales", dni, unique_filename)
        
        # Ruta completa para guardar el archivo
        file_path = os.path.join(user_dir, unique_filename)

        # Guardar archivo en disco
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Insertar en la base de datos (usando la ruta relativa)
        cursor.execute(
            """
            INSERT INTO documentos 
            (usuario_id, nombre_archivo, ruta, estado, subido_en)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (usuario_id, unique_filename, relative_path, 'pendiente', datetime.now())
        )
        
        documento_id = cursor.fetchone()[0]
        conn.commit()

        return {
            "message": "Documento subido exitosamente",
            "documento_id": documento_id,
            "nombre_archivo": unique_filename,
            "ruta": relative_path,
            "estado": "pendiente"
        }

    except Exception as e:
        conn.rollback()
        # Eliminar archivo si se creó pero falló la inserción en la BD
        if 'file_path' in locals() and os.path.exists(file_path):
            os.remove(file_path)
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al procesar el documento: {str(e)}"
        )
        
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
        if 'file' in locals():
            await file.close()

 

@router.delete(
    "/documentos/{documento_id}",
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Documento eliminado exitosamente"},
        403: {"description": "No autorizado para eliminar este documento"},
        404: {"description": "Documento no encontrado"},
        500: {"description": "Error al eliminar el documento"}
    }
)
async def eliminar_documento(
    documento_id: int,
    request: Request,
    credentials: HTTPAuthorizationCredentials = Security(security),
    current_user: TokenData = Depends(get_current_user)
):
    """
    Endpoint para que RRHH elimine un documento.
    Solo usuarios con rol 'rrhh' pueden usar este endpoint.
    """
    if current_user.rol != "rrhh":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tiene permiso para realizar esta acción"
        )

    conn = get_connection()
    if not conn:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error de conexión a la base de datos"
        )

    cursor = None
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # 1. Obtener la información del documento
        cursor.execute("""
            SELECT d.id, d.ruta, d.estado, u.dni
            FROM documentos d
            JOIN usuarios u ON d.usuario_id = u.id
            WHERE d.id = %s
        """, (documento_id,))
        
        documento = cursor.fetchone()
        
        if not documento:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No se encontró el documento con ID {documento_id}"
            )
        
        # 2. Eliminar el archivo físico si existe
        # Primero intentamos con la ruta relativa almacenada en la BD
        ruta_original = os.path.join(get_base_storage_path(), 'storage', documento['ruta'])
        ruta_original = os.path.abspath(ruta_original)
        
        # Rutas alternativas donde podría estar el archivo
        rutas_a_eliminar = [
            ruta_original,
            # Buscar directamente en originales/dni/archivo
            os.path.join(
                get_base_storage_path(),
                'storage',
                'originales',
                documento['dni'],
                os.path.basename(documento['ruta'])
            ),
            # Buscar directamente en firmados/dni/archivo
            os.path.join(
                get_base_storage_path(),
                'storage',
                'firmados',
                documento['dni'],
                os.path.basename(documento['ruta'])
            )
        ]
        
        # Eliminar archivos si existen
        for ruta in rutas_a_eliminar:
            try:
                if os.path.exists(ruta) and os.path.isfile(ruta):
                    os.remove(ruta)
                    print(f"Archivo eliminado: {ruta}")
            except Exception as e:
                print(f"Advertencia: No se pudo eliminar el archivo {ruta}: {str(e)}")
        
        # 3. Eliminar registros relacionados en otras tablas
        try:
            # Eliminar registros en la tabla firmas
            cursor.execute("""
                DELETE FROM firmas 
                WHERE documento_id = %s
            """, (documento_id,))
            
            # 4. Finalmente, eliminar el documento
            cursor.execute("""
                DELETE FROM documentos 
                WHERE id = %s
                RETURNING id
            """, (documento_id,))
            
            if not cursor.fetchone():
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="No se pudo eliminar el registro de la base de datos"
                )
                
            conn.commit()
            
            return {"message": "Documento eliminado exitosamente"}
            
        except Exception as e:
            conn.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error al eliminar registros relacionados: {str(e)}"
            )
            
    except HTTPException:
        if conn:
            conn.rollback()
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al eliminar el documento: {str(e)}"
        )
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@router.get(
    "/documentos",
    responses={
        200: {"description": "Lista de documentos filtrados por año y mes"},
        403: {"description": "No autorizado - Se requiere rol de RRHH"},
        400: {"description": "Parámetros inválidos"},
        500: {"description": "Error al obtener documentos"}
    }
)
async def listar_todos_documentos(
    anio: int = None,
    mes: str = None,
    credentials: HTTPAuthorizationCredentials = Security(security),
    current_user: TokenData = Depends(get_current_user)
):
    """
    Endpoint para listar documentos, con opción de filtrar por año y mes.
    El filtrado se realiza basado en el nombre del archivo.
    """
    if current_user.rol != "rrhh":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Se requiere rol de RRHH para acceder a este recurso"
        )

    # Validar que si se especifica mes, también se especifique año
    if mes and not anio:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Debe especificar un año cuando filtra por mes"
        )

    # Mapeo de nombres de mes a números
    meses = {
        'enero': '01', 'febrero': '02', 'marzo': '03', 'abril': '04',
        'mayo': '05', 'junio': '06', 'julio': '07', 'agosto': '08',
        'septiembre': '09', 'octubre': '10', 'noviembre': '11', 'diciembre': '12'
    }
    
    conn = get_connection()
    if not conn:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error de conexión a la base de datos"
        )

    cursor = None
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Construir la consulta base
        query = """
            SELECT d.id, d.usuario_id, d.nombre_archivo, d.ruta, d.estado, 
                   d.subido_en, d.firmado_en, 
                   u.nombre as nombre_usuario, u.dni as usuario_dni
            FROM documentos d
            JOIN usuarios u ON d.usuario_id = u.id
            WHERE 1=1
        """
        
        params = []
        
        # Si se especificó año, filtrar por año
        if anio is not None:
            query += " AND d.nombre_archivo LIKE %s"
            params.append(f"%{anio}%")
        
        # Si se especificó mes, filtrar por mes
        if mes and anio:
            # Convertir mes a formato numérico de 2 dígitos si es un nombre
            mes_num = None
            mes_nombre = None
            
            if mes.lower() in meses:
                mes_num = meses[mes.lower()]
                mes_nombre = mes.lower()
            elif mes.isdigit() and 1 <= int(mes) <= 12:
                mes_num = f"{int(mes):02d}"
                # Buscar el nombre del mes para búsqueda por nombre también
                for nombre, num in meses.items():
                    if num == mes_num:
                        mes_nombre = nombre
                        break
            
            if mes_num:
                # Para meses numéricos, buscar tanto con 1 como con 2 dígitos
                mes_num_sin_cero = str(int(mes_num))  # Convierte '09' a '9'
                
                query += " AND ("
                conditions = []
                
                # Patrones para búsqueda numérica
                patterns = [
                    f"[_-]{mes_num}[_-]",     # _09_ o -09-
                    f"[_-]{mes_num}\\.",     # _09.
                    f"[_-]{mes_num}[^0-9]",   # _09 seguido de algo que no sea número
                    f"[_-]{mes_num}$",         # _09 al final
                    f"[_-]{mes_num_sin_cero}[_-]",    # _9_ o -9-
                    f"[_-]{mes_num_sin_cero}\\.",    # _9.
                    f"[_-]{mes_num_sin_cero}[^0-9]",  # _9 seguido de algo que no sea número
                    f"[_-]{mes_num_sin_cero}$"         # _9 al final
                ]
                
                # Agregar condiciones para los patrones numéricos
                for pattern in patterns:
                    conditions.append(f"d.nombre_archivo ~* %s")
                    params.append(pattern)
                
                # Si hay nombre de mes, agregar condición para búsqueda por nombre
                if mes_nombre:
                    conditions.append("LOWER(d.nombre_archivo) LIKE %s")
                    params.append(f"%{mes_nombre}%")
                
                # Unir todas las condiciones con OR
                query += " OR ".join(conditions)
                query += ")"
        
        # Ordenar por fecha de subida (más reciente primero)
        query += " ORDER BY d.subido_en DESC"
        
        # Ejecutar la consulta
        cursor.execute(query, params)
        documentos = cursor.fetchall()
        
        # Procesar los resultados
        for doc in documentos:
            if doc.get('subido_en'):
                doc['subido_en'] = doc['subido_en'].isoformat()
            if doc.get('firmado_en'):
                doc['firmado_en'] = doc['firmado_en'].isoformat()
        
        # Mensaje descriptivo
        mensaje = f"Se encontraron {len(documentos)} documentos"
        if anio is not None:
            mensaje += f" para el año {anio}"
            if mes is not None:
                mensaje += f" y mes de {mes.capitalize() if not mes.isdigit() else mes}"
        
        return {
            "message": mensaje,
            "documentos": documentos
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


@router.post(
    "/documentos/upload/lote",
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {"description": "Documentos subidos exitosamente"},
        400: {"description": "Formato de archivo no válido o error en los datos"},
        403: {"description": "No autorizado"},
        500: {"description": "Error al procesar los documentos"}
    }
)
async def upload_documentos_lote(
    request: Request,
    files: list[UploadFile] = File(..., description="Lista de archivos PDF a subir"),
    credentials: HTTPAuthorizationCredentials = Security(security),
    current_user: TokenData = Depends(get_current_user)
):
    """
    Endpoint para subir múltiples documentos a la vez.
    El DNI del empleado se extraerá de los primeros 8 dígitos del nombre del archivo.
    Solo usuarios con rol 'rrhh' pueden usar este endpoint.
    """
    # Verificar si el usuario tiene permiso de RRHH
    if current_user.rol != "rrhh":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tiene permiso para realizar esta acción"
        )

    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se han proporcionado archivos"
        )

    conn = get_connection()
    if not conn:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error de conexión a la base de datos"
        )

    cursor = None
    resultados = []
    errores = []
    
    try:
        cursor = conn.cursor()
        
        # Mapeo de meses para uso en todo el método
        meses = {
            1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril",
            5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto",
            9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"
        }
        
        def extraer_mes_anio(nombre_archivo):
            # Buscar patrones como _MM_ o _MM. o _MM$ o _MM- o -MM- o _Mes_ o -Mes-
            import re
            
            # Mapeo de nombres de mes a números
            meses_dict = {
                'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4,
                'mayo': 5, 'junio': 6, 'julio': 7, 'agosto': 8,
                'septiembre': 9, 'octubre': 10, 'noviembre': 11, 'diciembre': 12
            }
            
            # Buscar año (4 dígitos)
            anio_match = re.search(r'(?:^|[_-])(20\d{2})(?:$|[_-])', nombre_archivo)
            anio = int(anio_match.group(1)) if anio_match else datetime.now().year
            
            # Buscar mes numérico (1-12 o 01-12)
            mes_match = re.search(r'(?:^|[_-])(0?[1-9]|1[0-2])(?:$|[^0-9])', nombre_archivo)
            if mes_match:
                return int(mes_match.group(1)), anio
                
            # Buscar nombre del mes
            for mes_nombre, mes_num in meses_dict.items():
                if mes_nombre in nombre_archivo.lower():
                    return mes_num, anio
            
            # Si no se encuentra, usar el mes y año actual
            return datetime.now().month, anio
        
        for file in files:
            try:
                # Validar que el archivo sea PDF
                if not file.filename or not allowed_file(file.filename):
                    errores.append({
                        "archivo": file.filename,
                        "error": "Formato de archivo no válido. Solo se permiten archivos PDF"
                    })
                    continue
                
                # Extraer DNI de los primeros 8 dígitos del nombre del archivo
                nombre_archivo = os.path.splitext(file.filename)[0]
                dni = ""
                
                # Tomar solo los primeros 8 caracteres numéricos
                for char in nombre_archivo:
                    if char.isdigit() and len(dni) < 8:
                        dni += char
                    elif len(dni) == 8:
                        break
                
                if len(dni) != 8:
                    errores.append({
                        "archivo": file.filename,
                        "error": "No se pudo extraer un DNI válido (8 dígitos) del nombre del archivo"
                    })
                    continue
                
                # Verificar si el usuario existe y obtener su ID
                cursor.execute("SELECT id FROM usuarios WHERE dni = %s", (dni,))
                usuario = cursor.fetchone()
                if not usuario:
                    errores.append({
                        "archivo": file.filename,
                        "dni": dni,
                        "error": f"No se encontró el usuario con DNI {dni}"
                    })
                    continue
                    
                usuario_id = usuario[0]
                
                # Obtener mes y año del archivo
                mes_archivo, anio_archivo = extraer_mes_anio(file.filename)
                
                # Obtener mes y año actual
                now = datetime.now()
                mes_actual = now.month
                anio_actual = now.year
                
                # Validar rango permitido: desde Enero hasta el mes actual, dentro del año actual
                es_mes_valido = (
                    anio_archivo == anio_actual and 1 <= mes_archivo <= mes_actual
                )
                
                if not es_mes_valido:
                    errores.append({
                        "archivo": file.filename,
                        "dni": dni,
                        "error": f"Solo se permiten documentos desde Enero hasta {meses[mes_actual]} de {anio_actual}"
                    })
                    continue
                
                # Verificar si ya existe un documento con el mismo DNI, mes y año
                cursor.execute("""
                    SELECT COUNT(*) 
                    FROM documentos d
                    JOIN usuarios u ON d.usuario_id = u.id
                    WHERE u.dni = %s 
                    AND (
                        (d.nombre_archivo LIKE %s) OR
                        (d.nombre_archivo LIKE %s) OR
                        (d.nombre_archivo LIKE %s) OR
                        (d.nombre_archivo LIKE %s)
                    )
                """, (
                    dni,
                    f"%{mes_archivo:02d}_{anio_archivo}%",  # Formato 08_2025
                    f"%{mes_archivo}_{anio_archivo}%",     # Formato 8_2025
                    f"%{meses[mes_archivo].lower()}_{anio_archivo}%",  # Formato agosto_2025
                    f"%{meses[mes_archivo].capitalize()}_{anio_archivo}%"  # Formato Agosto_2025
                ))
                
                if cursor.fetchone()[0] > 0:
                    errores.append({
                        "archivo": file.filename,
                        "dni": dni,
                        "error": f"Ya existe un documento para el usuario con DNI {dni} en {mes_archivo:02d}/{anio_archivo}"
                    })
                    continue
                
                # Generar nombre del archivo con el formato DNI_Boleta_MES_ANO.pdf
                mes = meses[mes_archivo]
                ano = str(anio_archivo)
                file_extension = os.path.splitext(file.filename)[1].lower()
                
                # Nombre del archivo
                unique_filename = f"{dni}_Boleta_{mes}_{ano}{file_extension}"
                
                # Crear directorio para el usuario si no existe (usando DNI como nombre de carpeta)
                user_dir = os.path.join(STORAGE_PATH, dni)
                os.makedirs(user_dir, exist_ok=True)
                
                # Ruta relativa para guardar en la BD (sin el STORAGE_PATH base)
                relative_path = os.path.join("originales", dni, unique_filename)
                
                # Ruta completa para guardar el archivo
                file_path = os.path.join(user_dir, unique_filename)

                # Guardar archivo en disco
                with open(file_path, "wb") as buffer:
                    shutil.copyfileobj(file.file, buffer)

                # Insertar en la base de datos (usando la ruta relativa)
                cursor.execute(
                    """
                    INSERT INTO documentos 
                    (usuario_id, nombre_archivo, ruta, estado, subido_en)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (usuario_id, unique_filename, relative_path, 'pendiente', datetime.now())
                )
                
                documento_id = cursor.fetchone()[0]
                
                resultados.append({
                    "archivo_original": file.filename,
                    "archivo_guardado": unique_filename,
                    "dni": dni,
                    "documento_id": documento_id,
                    "ruta": relative_path,
                    "estado": "subido"
                })
                
            except Exception as e:
                errores.append({
                    "archivo": file.filename,
                    "dni": dni if 'dni' in locals() else "No identificado",
                    "error": f"Error al procesar el archivo: {str(e)}"
                })
                # Si se creó el archivo pero falló algo después, eliminarlo
                if 'file_path' in locals() and os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except:
                        pass
                continue
        
        conn.commit()
        
        return {
            "mensaje": "Procesamiento de archivos completado",
            "archivos_procesados": len(resultados),
            "archivos_exitosos": len([r for r in resultados if r["estado"] == "subido"]),
            "archivos_con_error": len(errores),
            "resultados": resultados,
            "errores": errores
        }
        
    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al procesar los documentos: {str(e)}"
        )
        
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@router.get(
    "/documentos/estado/{estado}",
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Lista de documentos filtrados por estado"},
        400: {"description": "Estado no válido"},
        403: {"description": "No autorizado"},
        500: {"description": "Error al obtener los documentos"}
    }
)
async def listar_documentos_por_estado(
    estado: str,
    request: Request,
    credentials: HTTPAuthorizationCredentials = Security(security),
    current_user: TokenData = Depends(get_current_user)
):
    """
    Endpoint para listar documentos filtrados por estado (pendiente o firmado).
    Solo usuarios con rol 'rrhh' pueden usar este endpoint.
    """
    # Verificar si el usuario tiene permiso de RRHH
    if current_user.rol != "rrhh":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tiene permiso para realizar esta acción"
        )
    
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
        
        # Consulta para obtener los documentos filtrados por estado
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
                d.estado = %s
            ORDER BY 
                d.subido_en DESC
        """, (estado,))
        
        documentos = cursor.fetchall()
        
        # Convertir los resultados a un formato adecuado
        documentos_lista = []
        for doc in documentos:
            # Construir la URL completa para acceder al archivo
            base_url = str(request.base_url)
            if base_url.endswith('/'):
                base_url = base_url[:-1]
            
            # Eliminar '/docs' si está presente en la URL base
            if base_url.endswith('/docs'):
                base_url = base_url[:-5]
                
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


@router.get(
    "/documentos/periodos",
    responses={
        200: {"description": "Lista de años y meses disponibles en los documentos"},
        403: {"description": "No autorizado - Se requiere rol de RRHH"},
        500: {"description": "Error al obtener los períodos"}
    }
)
async def obtener_periodos_documentos(
    credentials: HTTPAuthorizationCredentials = Security(security),
    current_user: TokenData = Depends(get_current_user)
):
    """
    Endpoint para obtener los años y meses disponibles en los documentos.
    Solo usuarios con rol 'rrhh' pueden usar este endpoint.
    
    Retorna un diccionario con:
    - years: Lista de años únicos
    - months: Diccionario donde la clave es el año y el valor es la lista de meses disponibles
    """
    # Verificar si el usuario tiene permiso de RRHH
    if current_user.rol != "rrhh":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Se requiere rol de RRHH para acceder a este recurso"
        )

    conn = get_connection()
    if not conn:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error de conexión a la base de datos"
        )

    cursor = None
    try:
        cursor = conn.cursor()
        
        # Obtener todos los nombres de archivo
        cursor.execute("""
            SELECT nombre_archivo 
            FROM documentos
        """)
        
        # Mapeo de nombres de mes a números
        meses = {
            'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4,
            'mayo': 5, 'junio': 6, 'julio': 7, 'agosto': 8,
            'septiembre': 9, 'octubre': 10, 'noviembre': 11, 'diciembre': 12
        }
        
        years = set()
        months_by_year = {}
        
        for (filename,) in cursor.fetchall():
            # Extraer año (últimos 4 dígitos o los 4 dígitos después de _ o -)
            import re
            year_matches = re.findall(r'(?:^|[-_])(\d{4})(?:\.|$|_)', filename)
            if not year_matches:
                continue
                
            year = int(year_matches[0])
            
            # Extraer mes (puede ser número o nombre)
            month = None
            
            # Buscar patrón _MM_ o -MM- o _MM. o _MM al final
            num_match = re.search(r'[-_](\d{1,2})(?=[-_.]|$)', filename)
            if num_match:
                month = int(num_match.group(1))
            else:
                # Buscar nombre del mes
                for mes_nombre, mes_num in meses.items():
                    if mes_nombre in filename.lower():
                        month = mes_num
                        break
            
            if month is not None:
                years.add(year)
                if year not in months_by_year:
                    months_by_year[year] = set()
                months_by_year[year].add(month)
        
        # Convertir los sets a listas ordenadas
        years_list = sorted(years, reverse=True)
        months_dict = {}
        
        for year in years_list:
            months_dict[year] = sorted(months_by_year[year], reverse=True)
        
        return {
            "years": years_list,
            "months": months_dict
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener períodos de documentos: {str(e)}"
        )
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@router.post(
    "/documentos/upload/test",
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {"description": "Documento de prueba subido exitosamente"},
        400: {"description": "Formato de archivo no válido o parámetros inválidos"},
        403: {"description": "No autorizado para realizar esta acción"},
        500: {"description": "Error al procesar el documento"}
    }
)
async def upload_documento_test(
    request: Request,
    dni: str = Form(..., description="DNI del empleado dueño del documento"),
    mes: int = Form(..., description="Número de mes (1-12)", ge=1, le=12),
    anio: int = Form(..., description="Año (ej. 2023)", ge=2000, le=2100),
    file: UploadFile = File(..., description="Archivo PDF a subir"),
    credentials: HTTPAuthorizationCredentials = Security(security),
    current_user: TokenData = Depends(get_current_user)
):
    """
    Endpoint de prueba para subir documentos con mes y año personalizados.
    Solo para uso en entornos de prueba. No usar en producción.
    """
    # Verificar si el usuario tiene permiso de RRHH
    if current_user.rol != "rrhh":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tiene permiso para realizar esta acción"
        )

    # Validar que el archivo sea PDF
    if not file.filename or not allowed_file(file.filename):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Solo se permiten archivos PDF"
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
        cursor = conn.cursor()
        
        # Verificar si el usuario existe y obtener su ID
        cursor.execute("SELECT id FROM usuarios WHERE dni = %s", (dni,))
        usuario = cursor.fetchone()
        if not usuario:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No se encontró el usuario con DNI {dni}"
            )
            
        usuario_id = usuario[0]

        # Mapeo de meses (para nombre del archivo)
        meses = {
            1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril",
            5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto",
            9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"
        }
        mes_nombre = meses[mes]

        # Validar duplicados (por DNI, mes y año)
        cursor.execute(
            """
            SELECT COUNT(*) 
            FROM documentos d
            JOIN usuarios u ON d.usuario_id = u.id
            WHERE u.dni = %s 
            AND (
                (d.nombre_archivo LIKE %s) OR
                (d.nombre_archivo LIKE %s) OR
                (d.nombre_archivo LIKE %s) OR
                (d.nombre_archivo LIKE %s)
            )
            """,
            (
                dni,
                f"%{mes:02d}_{anio}%",               # 08_2025
                f"%{mes}_{anio}%",                   # 8_2025
                f"%{mes_nombre.lower()}_{anio}%",    # agosto_2025
                f"%{mes_nombre.capitalize()}_{anio}%" # Agosto_2025
            )
        )
        if cursor.fetchone()[0] > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Ya existe un documento para el usuario con DNI {dni} en {mes_nombre} de {anio}"
            )

        # Crear un nombre de archivo con el mismo formato que el endpoint por lote
        file_extension = os.path.splitext(file.filename)[1].lower()
        unique_filename = f"{dni}_Boleta_{mes_nombre}_{anio}{file_extension}"
        
        # Directorio del usuario y rutas
        user_dir = os.path.join(STORAGE_PATH, dni)
        os.makedirs(user_dir, exist_ok=True)
        file_path = os.path.join(user_dir, unique_filename)

        # Ruta relativa con '/' para URLs correctas
        relative_path = "/".join(["originales", dni, unique_filename])

        # Guardar el archivo
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Crear fecha personalizada con el mes y año proporcionados (día 1)
        from datetime import datetime
        try:
            custom_date = datetime(anio, mes, 1)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Fecha inválida: {str(e)}"
            )

        # Insertar el documento en la base de datos
        cursor.execute(
            """
            INSERT INTO documentos 
            (usuario_id, nombre_archivo, ruta, estado, subido_en)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                usuario_id,
                unique_filename,
                relative_path,
                'pendiente',
                custom_date
            )
        )
        
        documento_id = cursor.fetchone()[0]
        conn.commit()

        return {
            "mensaje": "Documento de prueba subido exitosamente",
            "documento_id": documento_id,
            "nombre_archivo": unique_filename,
            "ruta": relative_path,
            "mes": mes,
            "anio": anio,
            "dni": dni
        }

    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        # Eliminar el archivo si se creó pero falló la inserción en la base de datos
        if 'file_path' in locals() and os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al procesar el documento: {str(e)}"
        )
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
        if file.file:
            file.file.close()

def get_base_storage_path():
    """
    Retorna la ruta absoluta al folder 'app' dentro de tu proyecto,
    sin duplicar 'app'.
    """
    return os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))  # sube 3 niveles
