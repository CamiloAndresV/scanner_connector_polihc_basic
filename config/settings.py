# config/settings.py

"""
Este módulo define la configuración central de la aplicación utilizando 
la biblioteca pydantic-settings para gestionar variables de
entorno de forma segura y estructurada.
"""

# 1. Standard library imports
import sys
from pathlib import Path
from typing import Literal

# 2. Third party imports
from pydantic import Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """
    Clase de configuración que hereda de BaseSettings para gestionar variables de entorno.
    """
    model_config = SettingsConfigDict(  # aca se configura como base settings cargara los valores
        env_file=".env",  # le indica a pydantic que busque un archivo .env en el directorio actual
        env_file_encoding="utf-8",  # codificacion del archivo .env
        extra="ignore",  # Ignora variables en .env que no estén definidas aquí, solo lo necesario
        case_sensitive=False  # No distingue mayúsculas/minúsculas en nombres de variables
    )

    secret_key: str = Field(
        ...,
        min_length=25,
        description="Clave secreta para JWT y sesiones"
    )
    
    django_url: str = Field(
        "http://localhost:8000",
        description="URL base del servidor Django"
    )
    
    swagger_password: str = Field(
        ...,
        min_length=8,
        description="Contraseña para proteger la documentación Swagger"
    )
    
    swagger_user: str = Field(
        ...,
        min_length=4,
        description="Usuario para proteger la documentación Swagger"
    )
    
    debug: bool = Field(
        default=False,
        description="Modo de depuración (True=desarrollo, False=producción)"
    )
    
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        description="Nivel de logging (DEBUG, INFO, WARNING, ERROR, CRITICAL)"
    )

    flask_shared_secret: str | None = Field(
        default=None,
        description="Clave compartida para validar JWT HS256 emitidos por Django"
    )

    flask_require_auth: bool = Field(
        default=False,
        description="Si es True, exige JWT Bearer en endpoints /api/scan/*"
    )

    flask_jwt_issuer: str = Field(
        default="django-polihc",
        description="Issuer esperado en JWT de Django"
    )
    
    scanner_name: str = Field(
        default="Type301 Scanner",
        description="Nombre del escáner"
    )

    scanner_name_secondary: str = Field(
        default="e-STUDIO2822ASeries Scan Driver",
        description="Nombre secundario del escáner para fallback automático"
    )

    scanner_auto_fallback: bool = Field(
        default=False,
        description="Permite fallback automático al escáner secundario"
    )
    
    feeder_timeout: int = Field(
        default=7,
        description="Tiempo de espera para el alimentador automático (en segundos)"
    )
    
    flatbed_connection_timeout: int = Field(
        default=12,
        description="Tiempo de espera para la conexión al escáner de cristal (en segundos)"
    )
    
    flatbed_scan_timeout: int = Field(
        default=35,
        description="Tiempo de espera para completar el escaneo en cristal (en segundos)"
    )

    cleanup_schedule_hour: int = Field(
        ...,
        ge=0,
        le=23,
        description="Hora diaria para limpieza automática (0-23)"
    )

    cleanup_schedule_minute: int = Field(
        ...,
        ge=0,
        le=59,
        description="Minuto diario para limpieza automática (0-59)"
    )

    cleanup_session_timeout_minutes: int = Field(
        ...,
        ge=20,
        description="Minutos de inactividad/expiración para limpiar sesiones"
    )

    scan_image_format: Literal["webp", "png"] = Field(
        default="webp",
        description="Formato de imagen generado (webp o png)"
    )

    scan_image_quality: int = Field(
        default=85,
        ge=1,
        le=100,
        description="Calidad de compresión para WEBP (1-100)"
    )

    scan_image_method: int = Field(
        default=4,
        ge=0,
        le=6,
        description="Método de compresión WEBP (0-6, mayor = más compresión)"
    )

    scan_image_lossless: bool = Field(
        default=False,
        description="WEBP sin pérdida; puede aumentar el peso"
    )
    
    tesseract_cmd: str = Field(
        default=r"C:\Program Files\Tesseract-OCR\tesseract.exe", #C:\Program Files (x86)\Tesseract-OCR\tesseract.exe 
        description="Ruta al ejecutable de Tesseract OCR"
    )

# Instancia de la configuración que se usará en toda la aplicación
try:
    settings = Settings()
except ValidationError as e:
    print("❌ Error al cargar configuración:", file=sys.stderr)
    for error in e.errors():
        field = error["loc"][0]
        msg = error["msg"]
        print(f"  • {field}: {msg}", file=sys.stderr)

    env_path = Path(".env")
    if not env_path.exists():
        print("\n⚠️  Crea un archivo .env con:", file=sys.stderr)
        print("   SECRET_KEY=tu_clave_secreta_de_al_menos_25_caracteres", file=sys.stderr)
        print("   SWAGGER_PASSWORD=tu_contraseña_de_al_menos_8_caracteres", file=sys.stderr)
        print("   LOG_LEVEL=INFO", file=sys.stderr)
        print("   DEBUG=False", file=sys.stderr)
        print("   CLEANUP_SCHEDULE_HOUR=15", file=sys.stderr)
        print("   CLEANUP_SCHEDULE_MINUTE=30", file=sys.stderr)
        print("   CLEANUP_SESSION_TIMEOUT_MINUTES=20", file=sys.stderr)
        print("   FLASK_REQUIRE_AUTH=False", file=sys.stderr)
        print("   FLASK_SHARED_SECRET=clave_compartida_con_django", file=sys.stderr)

    sys.exit(1)
