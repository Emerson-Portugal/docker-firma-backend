from fastapi import APIRouter, HTTPException, status, Depends
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from jose import JWTError, jwt
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, EmailStr, Field

from app.database import get_connection
from app.models.user import UsuarioInDB, UsuarioLogin, RolUsuario

# Configuración del JWT
SECRET_KEY = "supersecreto_123"  # Debería estar en variables de entorno
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 600

router = APIRouter(
    prefix="/auth",
    tags=["Autenticación"],
)

# Esquema OAuth2
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    user: dict

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def authenticate_user(dni: str, password: str):
    conn = get_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Error de conexión a la base de datos")
    
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, dni, nombre, email, password, rol, activo, creado_en 
            FROM usuarios 
            WHERE dni = %s
            """,
            (dni,)
        )
        user_data = cursor.fetchone()
        
        if not user_data:
            return False
            
        # En una implementación real, deberías verificar la contraseña hasheada
        # Por ejemplo, usando passlib con bcrypt
        # if not verify_password(password, user_data['password']):
        #     return False
        
        # Por ahora, comparamos las contraseñas directamente (NO SEGURO PARA PRODUCCIÓN)
        if user_data[4] != password:  # password está en la posición 4
            return False
            
        return {
            "id": user_data[0],
            "dni": user_data[1],
            "nombre": user_data[2],
            "email": user_data[3],
            "rol": user_data[5],
            "activo": user_data[6],
            "creado_en": user_data[7]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al autenticar usuario: {str(e)}")
    finally:
        conn.close()

@router.post("/login", response_model=TokenResponse)
async def login(usuario: UsuarioLogin):
    user = await authenticate_user(usuario.dni, usuario.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="DNI o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user["activo"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Usuario inactivo"
        )
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user["dni"], "rol": user["rol"]}, 
        expires_delta=access_token_expires
    )
    
    # No devolvemos la contraseña
    user.pop("password", None)
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": user
    }

async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No se pudieron validar las credenciales",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        dni: str = payload.get("sub")
        if dni is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
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
        columns = [desc[0] for desc in cursor.description]
        user_data = cursor.fetchone()
        
        if user_data is None:
            raise credentials_exception
            
        # Convertir a diccionario
        user_dict = dict(zip(columns, user_data))
        return UsuarioInDB(**user_dict)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener el usuario: {str(e)}"
        )
    finally:
        conn.close()

@router.get("/me", response_model=UsuarioInDB)
async def read_current_user(current_user: UsuarioInDB = Depends(get_current_user)):
    return current_user
