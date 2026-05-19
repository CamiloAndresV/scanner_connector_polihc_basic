# app.py

"""
Archivo principal donde se levanta la API Flask que es el servidor de la aplicación.
Aquí se configuran imports de otros módulos, CORS que permite el acceso desde el frontend, 
blueprints (endpoints) que se utilizan para organizar las rutas de forma modular y 
el punto de entrada.
"""

# 1. Standard library imports
import os
import logging
import signal # captura de señales del sistema operativo
import sys # para interaccion con el interprete de Python (salir, argumentos, etc)

# 2. Third party imports
from flask import Flask, jsonify, request, Response
from flask_cors import CORS # permite que el frontend acceda a esta API
from rich.logging import RichHandler # mejora visual de los logs en consola para que no sea solo texto plano
from flasgger import Swagger # documentacion semi/automatica e interactiva de la API 

# 3. First party (local) imports
from config.settings import settings
from controllers.scan_controller import scan_bp

_server_shutting_down = False # bandera para evitar múltiples ejecuciones de shutdown/cierre simultaneas, solo se ejecutara la logica de cierre una vez
_cleanup_scheduler = None # referencia de scheduler(planificador/programador de tareas) que limpia sesiones antiguas

# Convertir log_level a constante de logging, por ejemplo logging.DEBUG o logging.INFO dependiendo del .env si esta configurado, sino por defecto es INFO
if hasattr(settings, 'log_level'):
    if isinstance(settings.log_level, str): # si es string, convertir a constante logging
        log_level = getattr(logging, settings.log_level.upper(), logging.INFO)
    else:
        log_level = settings.log_level # si ya es constante logging, usar directamente
else:
    log_level = logging.INFO

# Configuracion de Swagger SOLO en modo desarrollo (según variable DEBUG)
# En producción, Swagger estará completamente deshabilitado para evitar exponer la API
is_development = settings.debug

# Configuración del logging para la aplicación Flask
logging.basicConfig(
    level=log_level, 
    handlers=[RichHandler(rich_tracebacks=is_development)], 
    format="%(message)s",
    datefmt="[%X]"
    ) # subi el nivel de logging a DEBUG para no ser tan estricto (el level se puede poner en NOTSET para ver todo)

logger = logging.getLogger(__name__) # Logger específico para este módulo, permite identificar de donde vienen los logs


def validate_auth_configuration():
    """Valida configuración JWT obligatoria antes de iniciar servidor."""
    if settings.flask_require_auth and not settings.flask_shared_secret:
        logger.critical(
            "❌ FLASK_REQUIRE_AUTH=True pero FLASK_SHARED_SECRET no está configurado. "
            "Define FLASK_SHARED_SECRET en el entorno para iniciar."
        )
        sys.exit(1)

app = Flask(__name__) # Crear la aplicación Flask, la instancia principal
# app.secret_key = settings.secret_key # Clave secreta para sesiones y seguridad
if not hasattr(settings, 'secret_key') or not settings.secret_key:
    if is_development:
        logger.warning("⚠️ SECRET_KEY no configurada - usando clave temporal (solo desarrollo)")
        app.secret_key = os.urandom(24)
    else:
        logger.critical("❌ SECRET_KEY no configurada en .env - ABORTANDO en producción")
        sys.exit(1)
else:
    app.secret_key = settings.secret_key

swagger_template = { # estructura de la documentacion automatica para /apidocs/ para probar endpoints desde el navegador
    "swagger": "2.0",
    "info": {
        "title": "Scanner Connector API",
        "description": (
            "Documentación interactiva de la API Flask del conector de escaneo entre Django y el driver TWAIN.\n"
            "El prefijo para los endpoints de producción es /api/scan/*\n"
            "\n"
            "Esta API permite iniciar, cancelar y revisar el estado de los escaneos.\n"
            "También permite la configuración de parámetros como DPI, modo de color, tamaño de página, rotación, etc."
        ),
        "version": "1.0.0"
    },
    "basePath": "/",  # basePath común para todos los endpoints
    "schemes": ["http", "https"]
}

swagger_config = {
    "headers": [],
    "specs": [
        {
            "endpoint": 'apispec_1',
            "route": '/apispec_1.json',
            "rule_filter": lambda rule: True,  # incluir todas las rutas
            "model_filter": lambda tag: True,
        }
    ],
    "static_url_path": "/flasgger_static",
    "swagger_ui": True,
    "specs_route": "/apidocs/"
}


if is_development:
    # DESARROLLO: Swagger habilitado con autenticación por contraseña
    swagger = Swagger(app, template=swagger_template, config=swagger_config)
else:
    # PRODUCCIÓN: Swagger deshabilitado completamente
    swagger = None

allowed_origins = [
    "http://localhost:8000",
    "http://127.0.0.1:8000"
]

if hasattr(settings, 'django_url') and settings.django_url: # si en .env se definió DJANGO_URL, agregar a orígenes permitidos
    if settings.django_url not in allowed_origins:
        allowed_origins.append(settings.django_url)

CORS(app, resources={
    r"/api/*": {
        "origins": allowed_origins,
        "methods": ["GET", "POST", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"]
    }
}) #Los navegadores bloquean peticiones JavaScript entre dominios diferentes por seguridad. CORS le dice al navegador "confía, déjalo hacer peticiones".

# Registrar blueprints o módulos de rutas que agregan endpoints relacionados, es como importar
# y usar rutas específicas de otros archivos
app.register_blueprint(scan_bp)

# Proteger Swagger con autenticación (solo en modo desarrollo)
def check_swagger_auth():
    """
    Valida autenticación con usuario y contraseña para Swagger.
    En modo desarrollo: requiere credenciales del .env
    En modo producción: retorna 404 (Swagger deshabilitado)
    """
    # Si estamos en producción, Swagger no debe estar accesible
    if not is_development:
        return Response(
            jsonify({
                'error': 'Documentación deshabilitada',
                'message': 'Swagger UI no está disponible en producción'
            }).get_data(as_text=True),
            404,
            {'Content-Type': 'application/json'}
        )
    
    # En desarrollo: validar usuario y contraseña
    auth = request.authorization
    swagger_user = getattr(settings, 'swagger_user', None)
    swagger_password = getattr(settings, 'swagger_password', None)
    
    if not swagger_user or not swagger_password:
        logger.error("⚠️ SWAGGER_USER o SWAGGER_PASSWORD no configuradas en .env")
        return Response(
            'Error de configuración del servidor: credenciales de Swagger no establecidas',
            500
        )
    
    # Si no hay credenciales, pedir autenticación
    if not auth:
        return Response(
            'Autenticación requerida para acceder a la documentación',
            401,
            {'WWW-Authenticate': 'Basic realm="Swagger UI"'}
        )
    
    # Validar usuario Y contraseña
    if auth.username != swagger_user or auth.password != swagger_password:
        logger.warning(f"[SWAGGER] Intento de acceso fallido (usuario: {auth.username})")
        return Response(
            'Usuario o contraseña incorrectos',
            401,
            {'WWW-Authenticate': 'Basic realm="Swagger UI"'}
        )
    
    # Credenciales correctas
    logger.debug(f"[SWAGGER] Acceso autorizado (usuario: {auth.username})")
    return None
        
@app.before_request
def before_request():
    """
    Proteger /apidocs/ según el modo de ejecución.
    - DESARROLLO: Requiere autenticación por contraseña
    - PRODUCCIÓN: Retorna 404 (documentación deshabilitada)
    """
    if request.path.startswith('/apidocs'):
        auth_response = check_swagger_auth()
        if auth_response:
            return auth_response

# Ruta raíz para verificar que la API está funcionando
@app.route('/')
def index():
    """
    Ruta raíz para verificar que la API está funcionando
    """
    return {
        "message": "Scanner Connector API",
        "status": "running",
        "version": "1.0",
        "endpoints": {
            "production": "/api/scan/*"
        }
    }
    
def graceful_shutdown(signum=None, frame=None):
    """
    Cierra la aplicación de forma limpia sin errores de sockets
    evita ejecutar múltiples veces la lógica de cierre
    libera recursos, detiene scheduler y resetea estado
    """
    global _server_shutting_down, _cleanup_scheduler
    
    if _server_shutting_down:
        return
    _server_shutting_down = True
    
    logger.info("[SHUTDOWN] Apagando servidor...")
    
    # Detener scheduler
    if _cleanup_scheduler:
        try:
            _cleanup_scheduler.shutdown(wait=False) # no espera tareas en ejecución
        except Exception as e:
            logger.warning(f"[SHUTDOWN] Error deteniendo scheduler: {e}")
    
    # Resetear estado
    try:
        from controllers.scan_controller import reset_scan_state, state_lock, _hardware_lock
        with state_lock: # asegurar acceso exclusivo al estado, para evitar que otro hilo lo modifique mientras se resetea
            reset_scan_state()
    except Exception as e:
        logger.debug(f"[SHUTDOWN] Error reseteando estado: {e}")
    
    # Liberar hardware lock para evitar que el driver TWAIN quede bloqueado
    try:
        _hardware_lock.release() # liberar lock si está tomado
        logger.debug("✅ Hardware lock liberado correctamente")
    except RuntimeError:
        # Lock ya estaba liberado, esto es normal
        logger.debug("ℹ️ Hardware lock ya estaba liberado")
        pass
    logger.info("[SHUTDOWN] Completado")
    sys.exit(0)

# Registrar solo SIGINT, señal de interrupción de teclado (Ctrl+C)
signal.signal(signal.SIGINT, graceful_shutdown) # para que capture Ctrl+C en consola y cierre limpio


def validate_scanner_config():
    """
    Valida que el escáner configurado existe al iniciar la aplicación.
    Esto permite detectar errores de configuración inmediatamente en lugar de al intentar escanear.
    """
    sm = None
    try:
        import twain
        import ctypes
        
        logger.info("🔍 Validando configuración del escáner...")
        
        # Cargar TWAIN y usar una ventana válida para mayor compatibilidad de drivers.
        ctypes.windll.kernel32.SetDllDirectoryW(None)
        hwnd = ctypes.windll.user32.GetForegroundWindow() or ctypes.windll.user32.GetDesktopWindow() or 0
        sm = twain.SourceManager(hwnd)
        
        if not sm:
            logger.warning("⚠️ TWAIN no disponible - el escáner puede no funcionar correctamente")
            return False
        
        # Obtener lista de escáneres disponibles
        available_scanners = sm.GetSourceList() or []
        configured_scanner = settings.scanner_name
        
        if configured_scanner not in available_scanners:
            logger.error("=" * 70)
            logger.error("❌ ERROR DE CONFIGURACIÓN DEL ESCÁNER")
            logger.error(f"")
            logger.error(f"Escáner configurado en .env: '{configured_scanner}'")
            logger.error(f"Este escáner NO está disponible en el sistema.")
            logger.error(f"")
            logger.error(f"Escáneres disponibles:")
            for scanner in available_scanners:
                logger.error(f"  ✓ {scanner}")
            logger.error(f"")
            logger.error(f"Soluciones:")
            logger.error(f"  1. Verifica que el escáner esté encendido y conectado")
            logger.error(f"  2. Actualiza SCANNER_NAME en el archivo .env con uno de los nombres de arriba")
            logger.error(f"  3. Reinicia la aplicación después de corregir")
            logger.error("=" * 70)
            return False
        
        logger.info(f"✅ Escáner configurado correctamente: '{configured_scanner}'")
        return True
        
    except Exception as e:
        logger.warning(
            f"⚠️ No se pudo validar la configuración del escáner: {type(e).__name__}: {e!r}"
        )
        logger.warning(f"   La aplicación continuará, pero pueden ocurrir errores al escanear")
        return False
    finally:
        try:
            if sm is not None:
                sm.destroy()
        except Exception:
            logger.debug("No se pudo liberar SourceManager durante validación", exc_info=True)

def validate_tesseract():
    """Valida que Tesseract esté instalado si se usa auto-rotación."""
    tesseract_path = settings.tesseract_cmd
    if not os.path.exists(tesseract_path):
        logger.warning("=" * 70)
        logger.warning("⚠️ TESSERACT NO ENCONTRADO")
        logger.warning(f"Ruta configurada: {tesseract_path}")
        logger.warning("La auto-rotación (rotation='auto') no funcionará.")
        logger.warning("Instalar desde: https://docs.coro.net/featured/agent/install-tesseract-windows")
        logger.warning("=" * 70)
        return False
    logger.info(f"✅ Tesseract encontrado: {tesseract_path}")
    return True

if __name__ == "__main__": # esta parte del codigo solo se ejecuta si se corre app.py directamente, sino se importa como modulo y no se ejecuta
    logger.info(f"📝 Logging configurado en nivel: {logging.getLevelName(log_level)}")
    logger.info("Flask application initialized and blueprints registered.")
    validate_auth_configuration()
    
    # Validar configuración del escáner antes de iniciar
    validate_scanner_config()
    validate_tesseract()
    
    try:
        from utils.cleanup_scheduler import schedule_cleanup
        try:
            # Programar limpieza diaria usando configuración de las variales de entorno, si no se configuran usa los valores por defecto definidos en Settings
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
            _cleanup_scheduler = None

        logger.info(f"🚀 Modo: {'DESARROLLO' if is_development else 'PRODUCCIÓN'}")
        
        # Mostrar estado de Swagger según el modo
        if is_development:
            logger.info("📚 Swagger UI: http://127.0.0.1:5000/apidocs/")
        else:
            logger.info("🔒 Swagger UI: DESHABILITADO en producción")
        
        logger.info("🌐 Flask application is running on http://127.0.0.1:5000")

        # Iniciar la aplicación Flask en modo desarrollo
        # Para producción, se debe usar run_production.py o run_with_console.py
        app.run(
            debug=is_development,
            use_reloader=False, # Desactivar recarga automática para evitar múltiples instancias
            host='127.0.0.1',  # Solo conexiones locales
            port=5000,         # Puerto estándar
            threaded=True     # Habilitar manejo de múltiples hilos
        )
    except KeyboardInterrupt:
        logger.info("⏹️ Servidor detenido por usuario")
        graceful_shutdown()
    except OSError as e:
        if e.errno == 10048:  # Puerto ocupado en Windows
            logger.error(f"❌ Puerto 5000 ya está en uso")
        else:
            logger.exception(f"❌ Error del sistema: {e}")
        sys.exit(1) # esto termina la ejecucion de un programa y devuelve un codigo de estado al sistema operativo, si es 0 es exito, si es distinto de 0 es error
    except Exception as e:
        logger.exception(f"❌ Error fatal en servidor: {e}")
        graceful_shutdown() # cierre limpio en caso de error fatal