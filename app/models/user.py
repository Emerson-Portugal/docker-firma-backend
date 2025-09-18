from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, EmailStr, Field, validator
from enum import Enum

class RolUsuario(str, Enum):
    EMPLEADO = 'empleado'
    RRHH = 'rrhh'
    ADMIN = 'admin'
    SOPORTE = 'soporte'


class UsuarioBase(BaseModel):
    dni: str = Field(..., min_length=8, max_length=15, description="DNI del usuario")
    nombre: str = Field(..., max_length=150, description="Nombre completo del usuario")
    email: Optional[EmailStr] = Field(None, max_length=150, description="Correo electrónico del usuario")
    rol: RolUsuario = Field(default=RolUsuario.EMPLEADO, description="Rol del usuario en el sistema")
    activo: bool = Field(default=True, description="Indica si el usuario está activo en el sistema")

class UsuarioCreate(UsuarioBase):
    password: str = Field(..., min_length=8, description="Contraseña del usuario")

class UsuarioUpdate(BaseModel):
    nombre: Optional[str] = Field(None, max_length=150, description="Nombre completo del usuario")
    email: Optional[EmailStr] = Field(None, max_length=150, description="Correo electrónico del usuario")
    password: Optional[str] = Field(None, min_length=8, description="Nueva contraseña del usuario")
    rol: Optional[RolUsuario] = Field(None, description="Rol del usuario en el sistema")
    activo: Optional[bool] = Field(None, description="Indica si el usuario está activo en el sistema")

class UsuarioInDB(UsuarioBase):
    id: int
    creado_en: datetime = Field(default_factory=datetime.utcnow, description="Fecha de creación del usuario")

    class Config:
        orm_mode = True

class UsuarioLogin(BaseModel):
    dni: str = Field(..., description="DNI del usuario")
    password: str = Field(..., description="Contraseña del usuario")