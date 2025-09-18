from fastapi import APIRouter, HTTPException, status, Depends
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field
from enum import Enum

from app.database import get_connection
from app.models.user import UsuarioInDB, UsuarioCreate, UsuarioUpdate, RolUsuario
from app.api.endpoints.auth.auth_controller import get_current_user

router = APIRouter(
    prefix="/soporte",
    tags=["Soporte"],
    responses={404: {"description": "No encontrado"}},
)

# Función para verificar si el usuario tiene rol de soporte
async def get_soporte_user(current_user: UsuarioInDB = Depends(get_current_user)):
    if current_user.rol != "soporte":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tiene permisos para acceder a este recurso"
        )
    return current_user

@router.post("/usuarios/", response_model=UsuarioInDB, status_code=status.HTTP_201_CREATED)
async def crear_usuario(
    usuario: UsuarioCreate,
    current_user: UsuarioInDB = Depends(get_soporte_user)
):
    """
    Crea un nuevo usuario en el sistema.
    Solo accesible por usuarios con rol 'soporte'.
    """
    conn = get_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Error de conexión a la base de datos")
    
    try:
        cursor = conn.cursor()
        
        # Verificar si el DNI ya existe
        cursor.execute("SELECT id FROM usuarios WHERE dni = %s", (usuario.dni,))
        if cursor.fetchone():
            raise HTTPException(
                status_code=400,
                detail="Ya existe un usuario con este DNI"
            )
            
        # Insertar el nuevo usuario
        cursor.execute(
            """
            INSERT INTO usuarios (dni, nombre, email, password, rol, activo, creado_en)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id, dni, nombre, email, rol, activo, creado_en
            """,
            (
                usuario.dni,
                usuario.nombre,
                usuario.email,
                usuario.password,  # En producción, hashear la contraseña
                usuario.rol.value,
                usuario.activo,
                datetime.utcnow()
            )
        )
        
        new_user = cursor.fetchone()
        conn.commit()
        
        return {
            "id": new_user[0],
            "dni": new_user[1],
            "nombre": new_user[2],
            "email": new_user[3],
            "rol": new_user[4],
            "activo": new_user[5],
            "creado_en": new_user[6]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Error al crear el usuario: {str(e)}"
        )
    finally:
        if conn:
            conn.close()

@router.get("/usuarios/", response_model=List[UsuarioInDB])
async def listar_usuarios(
    skip: int = 0,
    limit: int = 100,
    current_user: UsuarioInDB = Depends(get_soporte_user)
):
    """
    Obtiene una lista de todos los usuarios.
    Solo accesible por usuarios con rol 'soporte'.
    """
    conn = get_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Error de conexión a la base de datos")
    
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, dni, nombre, email, rol, activo, creado_en
            FROM usuarios
            ORDER BY creado_en DESC
            LIMIT %s OFFSET %s
            """,
            (limit, skip)
        )
        
        usuarios = []
        for user in cursor.fetchall():
            usuarios.append({
                "id": user[0],
                "dni": user[1],
                "nombre": user[2],
                "email": user[3],
                "rol": user[4],
                "activo": user[5],
                "creado_en": user[6]
            })
            
        return usuarios
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error al obtener los usuarios: {str(e)}"
        )
    finally:
        if conn:
            conn.close()

@router.get("/usuarios/{dni}", response_model=UsuarioInDB)
async def obtener_usuario(
    dni: str,
    current_user: UsuarioInDB = Depends(get_soporte_user)
):
    """
    Obtiene un usuario por su DNI.
    Solo accesible por usuarios con rol 'soporte'.
    """
    conn = get_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Error de conexión a la base de datos")
    
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, dni, nombre, email, rol, activo, creado_en
            FROM usuarios
            WHERE dni = %s
            """,
            (dni,)
        )
        
        user = cursor.fetchone()
        if not user:
            raise HTTPException(
                status_code=404,
                detail="Usuario no encontrado"
            )
            
        return {
            "id": user[0],
            "dni": user[1],
            "nombre": user[2],
            "email": user[3],
            "rol": user[4],
            "activo": user[5],
            "creado_en": user[6]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error al obtener el usuario: {str(e)}"
        )
    finally:
        if conn:
            conn.close()

@router.put("/usuarios/{dni}", response_model=UsuarioInDB)
async def actualizar_usuario(
    dni: str,
    usuario: UsuarioUpdate,
    current_user: UsuarioInDB = Depends(get_soporte_user)
):
    """
    Actualiza un usuario existente por su DNI.
    Solo accesible por usuarios con rol 'soporte'.
    """
    conn = get_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Error de conexión a la base de datos")
    
    try:
        cursor = conn.cursor()
        
        # Verificar si el usuario existe
        cursor.execute("SELECT id FROM usuarios WHERE dni = %s", (dni,))
        user_data = cursor.fetchone()
        if not user_data:
            raise HTTPException(
                status_code=404,
                detail="Usuario no encontrado"
            )
        
        # Construir la consulta dinámica
        update_fields = []
        params = {}
        
        if usuario.nombre is not None:
            update_fields.append("nombre = %(nombre)s")
            params["nombre"] = usuario.nombre
            
        if usuario.email is not None:
            update_fields.append("email = %(email)s")
            params["email"] = usuario.email
            
        if usuario.password is not None:
            update_fields.append("password = %(password)s")
            params["password"] = usuario.password  # En producción, hashear la contraseña
            
        if usuario.rol is not None:
            update_fields.append("rol = %(rol)s")
            params["rol"] = usuario.rol.value
            
        if usuario.activo is not None:
            update_fields.append("activo = %(activo)s")
            params["activo"] = usuario.activo
        
        # Si no hay campos para actualizar, devolver error
        if not update_fields:
            raise HTTPException(
                status_code=400,
                detail="No se proporcionaron datos para actualizar"
            )
        
        # Agregar el DNI a los parámetros
        params["dni"] = dni
        
        # Construir y ejecutar la consulta SQL
        update_query = f"""
            UPDATE usuarios
            SET {", ".join(update_fields)}
            WHERE dni = %(dni)s
            RETURNING id, dni, nombre, email, rol, activo, creado_en
        """
        
        cursor.execute(update_query, params)
        updated_user = cursor.fetchone()
        conn.commit()
        
        if not updated_user:
            raise HTTPException(
                status_code=404,
                detail="No se pudo actualizar el usuario"
            )
            
        return {
            "id": updated_user[0],
            "dni": updated_user[1],
            "nombre": updated_user[2],
            "email": updated_user[3],
            "rol": updated_user[4],
            "activo": updated_user[5],
            "creado_en": updated_user[6]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Error al actualizar el usuario: {str(e)}"
        )
    finally:
        if conn:
            conn.close()

@router.delete("/usuarios/{dni}", status_code=status.HTTP_200_OK)
async def eliminar_usuario(
    dni: str,
    current_user: UsuarioInDB = Depends(get_soporte_user)
):
    """
    Elimina (desactiva) un usuario por su DNI.
    Solo accesible por usuarios con rol 'soporte'.
    """
    conn = get_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Error de conexión a la base de datos")
    
    try:
        cursor = conn.cursor()
        
        # Verificar si el usuario existe
        cursor.execute("SELECT id FROM usuarios WHERE dni = %s", (dni,))
        if not cursor.fetchone():
            raise HTTPException(
                status_code=404,
                detail="Usuario no encontrado"
            )
        
        # En lugar de eliminar, marcamos como inactivo (soft delete)
        cursor.execute(
            """
            UPDATE usuarios
            SET activo = FALSE
            WHERE dni = %s
            RETURNING id, dni, nombre
            """,
            (dni,)
        )
        
        deleted_user = cursor.fetchone()
        if not deleted_user:
            raise HTTPException(
                status_code=404,
                detail="No se pudo desactivar el usuario"
            )
            
        conn.commit()
        return {
            "mensaje": "Usuario desactivado correctamente",
            "usuario": {
                "id": deleted_user[0],
                "dni": deleted_user[1],
                "nombre": deleted_user[2]
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Error al desactivar el usuario: {str(e)}"
        )
    finally:
        if conn:
            conn.close()

@router.post("/usuarios/{dni}/activar", response_model=dict)
async def activar_usuario(
    dni: str,
    current_user: UsuarioInDB = Depends(get_soporte_user)
):
    """
    Activa un usuario por su DNI.
    Solo accesible por usuarios con rol 'soporte'.
    """
    conn = get_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Error de conexión a la base de datos")
    
    try:
        cursor = conn.cursor()
        
        # Verificar si el usuario existe
        cursor.execute("SELECT id, activo FROM usuarios WHERE dni = %s", (dni,))
        user_data = cursor.fetchone()
        
        if not user_data:
            raise HTTPException(
                status_code=404,
                detail="Usuario no encontrado"
            )
            
        user_id, is_active = user_data
        
        # Si ya está activo, devolver mensaje
        if is_active:
            return {
                "mensaje": "El usuario ya se encuentra activo",
                "dni": dni,
                "activo": True
            }
        
        # Activar el usuario
        cursor.execute(
            """
            UPDATE usuarios
            SET activo = TRUE
            WHERE dni = %s
            RETURNING id, dni, nombre, email
            """,
            (dni,)
        )
        
        updated_user = cursor.fetchone()
        if not updated_user:
            raise HTTPException(
                status_code=500,
                detail="No se pudo activar el usuario"
            )
            
        conn.commit()
        
        return {
            "mensaje": "Usuario activado correctamente",
            "usuario": {
                "id": updated_user[0],
                "dni": updated_user[1],
                "nombre": updated_user[2],
                "email": updated_user[3],
                "activo": True
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Error al activar el usuario: {str(e)}"
        )
    finally:
        if conn:
            conn.close()