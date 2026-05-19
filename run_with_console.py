"""
Script para ejecutar el servidor en modo producción con VENTANA DE CONSOLA PROTEGIDA.
La ventana mostrará los logs en tiempo real pero NO podrá cerrarse con el botón X.
Solo se puede detener con: Stop-ScheduledTask desde PowerShell.

Uso: python run_with_console.py
"""

import os
import sys
import logging
import signal
import ctypes
import socket
from logging.handlers import RotatingFileHandler
from datetime import datetime

# === SOPORTE DE COLORES EN WINDOWS ===
try:
    from colorama import init, Fore, Style
    init(autoreset=True)  # Auto-reset colores después de cada print
    COLORS_AVAILABLE = True
except ImportError:
    # Fallback si colorama no está instalado
    class Fore:
        RED = GREEN = YELLOW = BLUE = CYAN = MAGENTA = WHITE = RESET = ''
    class Style:
        BRIGHT = DIM = RESET_ALL = ''
    COLORS_AVAILABLE = False

# Asegurarse de que estamos en el directorio correcto
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Verificar que no estamos en modo debug
os.environ.setdefault('DEBUG', 'False')

# === BLOQUEO DE CIERRE DE VENTANA (WINDOWS API) ===
def disable_close_button():
    """Elimina el botón X de cierre de la ventana de consola usando Windows API."""
    try:
        kernel32 = ctypes.windll.kernel32
        user32 = ctypes.windll.user32
        
        # Obtener handle de la ventana de consola
        hwnd = kernel32.GetConsoleWindow()
        if hwnd:
            # Obtener menú del sistema
            hmenu = user32.GetSystemMenu(hwnd, 0)
            if hmenu:
                # SC_CLOSE = 0xF060 (comando de cerrar)
                user32.DeleteMenu(hmenu, 0xF060, 0x0)
                # Forzar actualización de la ventana
                user32.DrawMenuBar(hwnd)
                return True
        return False
    except Exception as e:
        print(f"⚠️  No se pudo bloquear el botón de cierre: {e}")
        return False

def set_console_title(title):
    """Establece el título de la ventana de consola."""
    try:
        ctypes.windll.kernel32.SetConsoleTitleW(title)
    except:
        pass


def get_machine_name():
    """Devuelve el nombre del equipo para mostrarlo al usuario."""
    return os.environ.get('COMPUTERNAME') or os.environ.get('HOSTNAME') or socket.gethostname()

# Ctrl+C está permitido - el servidor se puede cerrar con Ctrl+C normalmente
# Solo bloqueamos SIGTERM para evitar cierres no intencionados desde el sistema
def graceful_shutdown(signum, frame):
    """Handler para cierre ordenado del servidor."""
    print(f"\n{Fore.YELLOW}⚠️  Señal de terminación recibida. Cerrando servidor...{Style.RESET_ALL}")
    sys.exit(0)

signal.signal(signal.SIGTERM, graceful_shutdown)  # Terminación ordenada

# === FORMATEADOR DE COLORES PARA CONSOLA ===
class ColoredFormatter(logging.Formatter):
    """Formatter que agrega colores según el nivel de log."""
    
    COLORS = {
        'DEBUG': Fore.CYAN,
        'INFO': Fore.GREEN,
        'WARNING': Fore.YELLOW,
        'ERROR': Fore.RED,
        'CRITICAL': Fore.MAGENTA + Style.BRIGHT,
    }
    
    def format(self, record):
        # Guardar levelname original
        levelname_orig = record.levelname
        
        # Agregar color al levelname
        if COLORS_AVAILABLE and levelname_orig in self.COLORS:
            color = self.COLORS[levelname_orig]
            record.levelname = f"{color}{levelname_orig}{Style.RESET_ALL}"
            
            # Colorear timestamp en cyan claro
            formatted = super().format(record)
            # Agregar color al timestamp (primeros 8 caracteres = HH:MM:SS)
            formatted = f"{Fore.CYAN}{formatted[:8]}{Style.RESET_ALL}{formatted[8:]}"
        else:
            formatted = super().format(record)
        
        # Restaurar levelname original
        record.levelname = levelname_orig
        
        return formatted

# === CONFIGURACIÓN DE LOGGING (DUAL: CONSOLA + ARCHIVO) ===
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

# Archivo de log con rotación (SIN colores)
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

# Handler de consola CON COLORES
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(ColoredFormatter(
    '%(asctime)s | %(levelname)-8s | %(message)s',
    datefmt='%H:%M:%S'
))

# Configurar logging raíz con AMBOS handlers
logging.basicConfig(
    level=logging.INFO,
    handlers=[file_handler, console_handler]
)

logger = logging.getLogger('production')

# Capturar excepciones no manejadas
def handle_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        # Ctrl+C permitido - cerrar ordenadamente
        logger.info("Servidor detenido por usuario (Ctrl+C)")
        print(f"\n{Fore.GREEN}✓ Servidor detenido correctamente{Style.RESET_ALL}")
        sys.exit(0)
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
    # Configurar título y protección de ventana
    set_console_title("Scanner Connector API WITH CONSOLE - PRODUCCIÓN [PROTEGIDO]")
    
    console_protected = disable_close_button()
    
    # Banner con colores
    print(f"\n{Fore.CYAN}{Style.BRIGHT}╔══════════════════════════════════════════════════════════════════════════╗{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{Style.BRIGHT}║  SCANNER CONNECTOR API - PRODUCCIÓN (MODO VENTANA PROTEGIDA)             ║{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{Style.BRIGHT}╚══════════════════════════════════════════════════════════════════════════╝{Style.RESET_ALL}\n")

    machine_name = get_machine_name()
    print(f"{Fore.GREEN}✅ Conector activo. Este equipo se llama: {machine_name}{Style.RESET_ALL}")
    logger.info(f"Conector activo. Este equipo se llama: {machine_name}")
    
    # === VALIDACIONES AL INICIO (NUEVO) ===
    print(f"{Fore.CYAN}🔎 Validando entorno...{Style.RESET_ALL}")

    validate_auth_configuration()
    
    # 1. Validar TWAIN
    if not validate_scanner_config():
        print(f"{Fore.YELLOW}⚠️  No se pudo validar la configuración del escáner al iniciar. Revise logs.{Style.RESET_ALL}")
        # No salimos con sys.exit para permitir que al menos responda el health check, 
        # pero es una falla crítica operativa.
    
    # 2. Validar Tesseract
    if not validate_tesseract():
        print(f"{Fore.YELLOW}⚠️  Tesseract no encontrado. Auto-rotación deshabilitada.{Style.RESET_ALL}")

    if COLORS_AVAILABLE:
        print(f"{Fore.GREEN}✓ Colores habilitados (colorama detectado){Style.RESET_ALL}")
    else:
        print("⚠️  Colores no disponibles (instale: pip install colorama)")
    
    logger.info(f"Iniciado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"Servidor: http://127.0.0.1:5000")
    logger.info(f"Health Check: http://localhost:5000/api/scan/health")
    logger.info(f"Log file: {log_file}")
    
    if console_protected:
        logger.info("✅ Ventana protegida: Botón X deshabilitado")
        print(f"{Fore.GREEN}✅ Protección activa: No se puede cerrar con X{Style.RESET_ALL}")
    else:
        logger.warning("⚠️  No se pudo deshabilitar botón de cierre (requiere Windows)")
    
    print(f"{Fore.WHITE}───────────────────────────────────────────────────────────────────────────{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}⚠️  Para detener el servidor:{Style.RESET_ALL}")
    print(f"   {Fore.GREEN}• Ctrl+C en esta ventana{Style.RESET_ALL}")
    print(f"   {Fore.CYAN}• Stop-ScheduledTask -TaskName 'Scanner Connector API With Console'{Style.RESET_ALL}")
    print(f"{Fore.WHITE}───────────────────────────────────────────────────────────────────────────{Style.RESET_ALL}")
    print(f"\n{Fore.MAGENTA}{Style.BRIGHT}📊 LOGS EN TIEMPO REAL:{Style.RESET_ALL}\n")
    
    try:
        serve(
            app,
            host='127.0.0.1',
            port=5000,
            threads=4,
            url_scheme='http',
            ident='ScannerConnectorAPI'
        )
    except Exception as e:
        logger.critical(f"Error fatal al iniciar servidor: {e}", exc_info=True)
        print(f"\n{Fore.RED}{Style.BRIGHT}❌ ERROR FATAL: {e}{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}Revise el archivo de log para más detalles.{Style.RESET_ALL}")
        input(f"\n{Fore.CYAN}Presione Enter para cerrar...{Style.RESET_ALL}")
        raise