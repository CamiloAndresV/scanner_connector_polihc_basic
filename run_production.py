"""
Script para ejecutar el servidor en modo producción con Waitress.
Utiliza Waitress para servir la aplicación Flask de manera robusta.
uso: python run_production.py, este corre si se usa instalar_tarea.ps1  
"""

import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime

# Asegurarse de que estamos en el directorio correcto
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Verificar que no estamos en modo debug
os.environ.setdefault('DEBUG', 'False')

# === CONFIGURACIÓN DE LOGGING PARA PRODUCCIÓN ===
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

# Archivo principal de log con rotación (máx 5MB, 5 backups)
log_file = os.path.join(LOG_DIR, 'api_production.log')
file_handler = RotatingFileHandler(
    log_file,
    maxBytes=5*1024*1024,  # 5 MB
    backupCount=5,
    encoding='utf-8'
)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
))

# Configurar logging raíz
logging.basicConfig(
    level=logging.INFO,
    handlers=[file_handler]
)

# Logger específico para este módulo
logger = logging.getLogger('production')

# Capturar excepciones no manejadas para que queden en el log
def handle_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logger.critical("Excepción no manejada", exc_info=(exc_type, exc_value, exc_traceback))

sys.excepthook = handle_exception

# === IMPORTAR APP DESPUÉS DE CONFIGURAR LOGGING ===
from waitress import serve
from app import app, validate_scanner_config, validate_tesseract, validate_auth_configuration
from config.settings import settings

# === INICIALIZAR SCHEDULER DE LIMPIEZA ===
_cleanup_scheduler = None
try:
    from utils.cleanup_scheduler import schedule_cleanup
    _cleanup_scheduler = schedule_cleanup(
        hour=settings.cleanup_schedule_hour,
        minute=settings.cleanup_schedule_minute
    )
    logger.info(
        f"✅ Scheduler de limpieza iniciado (diario {settings.cleanup_schedule_hour:02d}:{settings.cleanup_schedule_minute:02d})"
    )
except Exception as e:
    logger.warning(f"⚠️ No se pudo iniciar scheduler automático: {e}")
    logger.warning("    Ejecute /api/scan/run-cleanup manualmente para limpiar sesiones")

if __name__ == '__main__':
    # Validaciones previas al inicio
    validate_auth_configuration()
    validate_scanner_config()
    validate_tesseract()

    startup_msg = f"""
================================================================================
  SCANNER CONNECTOR API - PRODUCCIÓN
  Iniciado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    Servidor: http://127.0.0.1:5000
    Health Check: http://localhost:5000/api/scan/health
  Log file: {log_file}
================================================================================
"""
    logger.info(startup_msg)
    print(startup_msg)  # También a consola si existe
    
    try:
        serve(
            app,
            host='127.0.0.1',
            port=5000,
            threads=4,  # Número de workers
            url_scheme='http',
            ident='ScannerConnectorAPI'  # Nombre en headers
        )
    except Exception as e:
        logger.critical(f"Error fatal al iniciar servidor: {e}", exc_info=True)
        raise