from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from pydantic import BaseModel, Field

from app.database import get_connection
from app.models.user import UsuarioInDB, RolUsuario

# Configuración del JWT (debe coincidir con auth_controller.py)
SECRET_KEY = "supersecreto_123"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 600

router = APIRouter(
    prefix="/auth/validate",
    tags=["Autenticación"],
    responses={
        401: {"description": "Token inválido o expirado"},
        500: {"description": "Error interno del servidor"}
    }
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

class TokenData(BaseModel):
    sub: str  # DNI del usuario
    rol: str

class TokenValidationResponse(BaseModel):
    is_valid: bool
    dni: str
    nombre: Optional[str] = None
    email: Optional[str] = None
    rol: str
    expires_in: int

async def get_current_user(token: str = Depends(oauth2_scheme)) -> TokenData:
    """
    Valida el token JWT y devuelve los datos del usuario si es válido.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No se pudo validar las credenciales",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        dni: str = payload.get("sub")
        rol: str = payload.get("rol")
        
        if dni is None or rol is None:
            raise credentials_exception
            
        return TokenData(sub=dni, rol=rol)
    except JWTError as e:
        raise credentials_exception

@router.get(
    "/token",
    response_model=TokenValidationResponse,
    summary="Validar token JWT",
    description="""
    Valida un token JWT y devuelve información sobre su validez.
    
    **Notas:**
    - El token debe ser enviado en el header de autorización (Bearer token)
    - Verifica la firma y la fecha de expiración
    - Devuelve información adicional del usuario desde la base de datos
    """
)
async def validate_token(
    request: Request,
    current_user: TokenData = Depends(get_current_user)
):
    """
    Endpoint para validar un token JWT y obtener información del usuario.
    """
    try:
        # Obtener información adicional del usuario desde la base de datos
        conn = get_connection()
        if not conn:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error de conexión a la base de datos"
            )
            
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, dni, nombre, email, rol, activo, creado_en 
            FROM usuarios 
            WHERE dni = %s
            """,
            (current_user.sub,)
        )
        columns = [desc[0] for desc in cursor.description]
        user_data = cursor.fetchone()
        
        if user_data is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Usuario no encontrado"
            )
            
        # Convertir a diccionario
        user = dict(zip(columns, user_data))
        
        # Obtener el token del header
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Formato de token inválido"
            )
            
        token = auth_header.split(" ")[1]
        
        # Verificar si el token está a punto de expirar
        payload = jwt.decode(
            token,
            SECRET_KEY, 
            algorithms=[ALGORITHM], 
            options={"verify_exp": False}
        )
        expires_at = datetime.fromtimestamp(payload["exp"])
        now = datetime.utcnow()
        expires_in = int((expires_at - now).total_seconds())
        
        return {
            "is_valid": True,
            "dni": user["dni"],
            "nombre": user["nombre"],
            "email": user["email"],
            "rol": user["rol"],
            "expires_in": max(0, expires_in)
        }
        
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token inválido: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al validar el token: {str(e)}"
        )
    finally:
        if 'conn' in locals() and conn:
            conn.close()

