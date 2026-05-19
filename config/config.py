# config/config.py

"""
    Configuración general de la aplicación.
    Aquí se definen las rutas, opciones de escaneo y otros parámetros necesarios 
    para el funcionamiento del escáner.
    Son las configuraciones base y por defecto que pueden ser modificadas 
    según las necesidades del usuario.
    También se asegura de crear las carpetas necesarias si no existen como la de scans.
"""

# 1. Standard library imports
import os # para manejo de rutas y sistema de archivos
import logging

# 2. Third party imports
from config.settings import settings

# Configuración del logger
logger = logging.getLogger(__name__)

FEEDER_TIMEOUT = settings.feeder_timeout   # segundos - ADF responde más rápido

# Timeouts bifásicos para cristal (flatbed)
FLATBED_CONNECTION_TIMEOUT = settings.flatbed_connection_timeout   # segundos - Fase 1: detectar si hardware responde (6-12s recomendado)
FLATBED_SCAN_TIMEOUT = settings.flatbed_scan_timeout       # segundos - Fase 2: esperar escaneo una vez iniciado

# Carpeta base del proyecto
# esto es dos niveles arriba, es decir la raiz del proyecto
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Carpeta para guardar las carpetas con las imagenes escaneados,
# dentro de la raiz del proyecto
SCAN_FOLDER = os.path.join(BASE_DIR, "scans")

# Configuración por defecto de escaneo
DEFAULT_DPI = 300 # 300, 400, 600
DEFAULT_COLOR_MODE = "Text" # 'Text', 'Text/Photo','Gray', 'Color'
DEFAULT_DUPLEX = False
DEFAULT_FEEDER = True
DEFAULT_PAGE_SIZE = "LT-R"  # 'LT-R', 'A4-R', '13-LG', "A5-R"
DEFAULT_ROTATION = "off" # 'off', 'right90', '180', 'left90', 'auto'
DEFAULT_SKIP_BLANK_PAGES = True

# Mapeo de tamaños según context.txt
PAGE_SIZES = {
    "LT-R": {"width": 216, "height": 279, "twain_code": "TWSS_USLETTER"},  # Carta
    "A4-R": {"width": 210, "height": 297, "twain_code": "TWSS_A4"},     # A4 intermedio
    "13-LG": {"width": 216, "height": 330, "twain_code": "TWSS_USLEGAL"},  # Oficio
    "A5-R": {"width": 148, "height": 210, "twain_code": "TWSS_A5"}, # A5 pequeño
}

# Modos de escaneo válidos
SCAN_MODES = ["Text/Photo", "Text", "Gray", "Color"]

# Resoluciones permitidas
ALLOWED_DPI = [300, 400, 600]

# Rotaciones permitidas
ROTATIONS = ["off", "right90", "180", "left90", "auto"]

# Crear la carpeta scans si no existe
if not os.path.exists(SCAN_FOLDER):
    os.makedirs(SCAN_FOLDER, exist_ok=True)
    logger.info(f"📁 Carpeta creada: {SCAN_FOLDER}")