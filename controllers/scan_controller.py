# controllers/scan_controller.py

"""
Controlador para endpoints relacionados con el escaneo de documentos.
Incluye lógica para iniciar escaneos, cancelar, revisar estado y limpieza de sesiones.
"""

# 1. Standard library imports 
import shutil
import os
from datetime import datetime
import logging
import threading

# 2. Third party imports
from flask import Blueprint, request, jsonify, send_from_directory
import jwt
from jwt import ExpiredSignatureError, ImmatureSignatureError, InvalidTokenError

# 3. First party (local) imports
from utils.session_lock import session_manager, LOCK_FILE
from utils.file_manager import ScanFileManager
from config.config import DEFAULT_DPI, DEFAULT_COLOR_MODE, DEFAULT_DUPLEX, DEFAULT_FEEDER, DEFAULT_PAGE_SIZE, DEFAULT_ROTATION, ALLOWED_DPI, SCAN_MODES, PAGE_SIZES, ROTATIONS, SCAN_FOLDER, FEEDER_TIMEOUT, DEFAULT_SKIP_BLANK_PAGES
from config.settings import settings  # Para validación de scanner_name
from services.twain_connector import scan_document, check_feeder, check_flatbed_sheet, validate_and_scan_flatbed, is_blank_page
from werkzeug.utils import secure_filename
from utils.image_orientation import auto_rotate_image
from flask import current_app
# Blueprint para endpoints de producción
scan_bp = Blueprint('scan', __name__, url_prefix='/api/scan')

logger = logging.getLogger(__name__)

def _unauthorized(message):
    """Respuesta estandarizada para autenticación fallida."""
    return jsonify({
        'success': False,
        'error': 'invalid_token',
    }), 401

@scan_bp.before_request
def require_jwt_auth():
    """Valida JWT Bearer para todos los endpoints de escaneo cuando está habilitado."""
    if not settings.flask_require_auth:
        return None

    if not settings.flask_shared_secret:
        logger.error("FLASK_SHARED_SECRET no configurado con auth activa")
        return _unauthorized('Configuración de autenticación inválida')

    auth_header = request.headers.get('Authorization', '').strip()
    if not auth_header.startswith('Bearer '):
        logger.warning(
            "[SECURITY] ip=%s endpoint=%s issuer=%s auth=denied reason=missing_bearer",
            request.remote_addr,
            request.path,
            settings.flask_jwt_issuer,
        )
        return _unauthorized('Token Bearer requerido')

    token = auth_header[len('Bearer '):].strip()
    if not token:
        logger.warning(
            "[SECURITY] ip=%s endpoint=%s issuer=%s auth=denied reason=empty_token",
            request.remote_addr,
            request.path,
            settings.flask_jwt_issuer,
        )
        return _unauthorized('Token Bearer requerido')

    try:
        payload = jwt.decode(
            token,
            settings.flask_shared_secret,
            algorithms=['HS256'],
            issuer=settings.flask_jwt_issuer,
            options={'require': ['exp', 'iss']},
            leeway=60,
        )
    except ExpiredSignatureError:
        logger.warning(
            "[SECURITY] ip=%s endpoint=%s issuer=%s auth=denied reason=expired_token",
            request.remote_addr,
            request.path,
            settings.flask_jwt_issuer,
        )
        return _unauthorized('Token expirado')
    except ImmatureSignatureError:
        logger.warning(
            "[SECURITY] ip=%s endpoint=%s issuer=%s auth=denied reason=immature_token",
            request.remote_addr,
            request.path,
            settings.flask_jwt_issuer,
        )
        return _unauthorized('Token aún no válido')
    except InvalidTokenError as exc:
        logger.warning(
            "[SECURITY] ip=%s endpoint=%s issuer=%s auth=denied reason=invalid_token detail=%s",
            request.remote_addr,
            request.path,
            settings.flask_jwt_issuer,
            exc.__class__.__name__,
        )
        return _unauthorized('Token inválido')

    logger.info(
        "[SECURITY] ip=%s endpoint=%s issuer=%s auth=ok",
        request.remote_addr,
        request.path,
        payload.get('iss'),
    )

    return None

# Estado global del escaneo actual
scan_state = {
    'is_scanning': False,
    'session_id': None,
    'user_id': None,
    'scanner_name': None,
    'file_manager': None,
    'progress': {
        'pages_scanned': 0,
        'status': 'idle',  # idle, scanning, completed, error, cancelled
        'message': '',
        'error': None
    }
}

# Lock para operaciones thread-safe
# Usamos RLock para permitir reentrancia cuando funciones internas también adquieren el lock
state_lock = threading.RLock()

def reset_scan_state():
    """Reinicia el estado del escaneo.
    Seguro de llamar con o sin state_lock gracias a RLock.
    """
    with state_lock:
        scan_state['is_scanning'] = False
        scan_state['session_id'] = None
        scan_state['user_id'] = None
        scan_state['scanner_name'] = None
        scan_state['file_manager'] = None
        scan_state['progress'] = {
            'pages_scanned': 0,
            'status': 'idle',
            'message': '',
            'error': None
        }

def restore_session_from_lock():
    """
    Restaura sesión sin importar si hay páginas o no.
    Funciona para cuando se apaga y prende el servidor mientras
    hay una sesión activa.
    
    - Si hay sesión activa (.lock) válida → restaura estado en memoria
    - Si la sesión expiró → limpia lock y carpeta
    - Si no hay lock → limpia carpetas huérfanas residuales
    """
    with state_lock:
        # Ya hay sesión en memoria, no hacer nada
        if scan_state['is_scanning'] and scan_state['session_id']:
            logger.info("Ya hay sesión activa en memoria, omitiendo restauración")
            return
        
        active_session = session_manager._get_active_session()
        
        # No hay lock, limpiar carpetas huérfanas
        if not active_session:
            logger.info("No hay sesión activa, revisando carpetas residuales...")
            perform_cleanup(force=False)  # Limpia solo carpetas expiradas
            return
        
        session_id = active_session.get('session_id')
        user_id = active_session.get('user_id')
        scanner_name = active_session.get('scanner_name')
        
        if not session_id:
            logger.warning("Lock existe pero no tiene session_id, ignorando")
            return
        
        # Verificar si la sesión expiró
        if session_manager._is_session_expired(active_session):
            logger.info(f"Sesión {session_id} expiró durante reinicio, limpiando...")
            try:
                session_manager.release_lock(session_id)
                fm = ScanFileManager(session_id)
                fm.cleanup_session()
            except Exception as e:
                logger.error(f"Error al limpiar sesión expirada: {e}")
            return
        
        try:
            file_manager = ScanFileManager(session_id)
            
            # Asegurar que la carpeta existe (puede haber sido borrada manualmente)
            if not os.path.exists(file_manager.session_folder):
                os.makedirs(file_manager.session_folder, exist_ok=True)
                logger.info(f"Carpeta de sesión recreada: {file_manager.session_folder}")
            
            pages_scanned = file_manager.get_page_count()  # Puede ser 0
            
            scan_state.update({
                'is_scanning': True,
                'session_id': session_id,
                'user_id': user_id,
                'scanner_name': scanner_name,
                'file_manager': file_manager,
                'progress': {
                    'pages_scanned': pages_scanned,
                    'status': 'ready',
                    'message': f'Sesión restaurada con {pages_scanned} páginas en Flask',
                    'error': None
                }
            })
            logger.info(f"✅ Sesión restaurada: session_id={session_id}, user={user_id}, pages={pages_scanned}")
            
        except Exception as e:
            logger.error(f"Error restaurando sesión {session_id}: {e}", exc_info=True)
            # NO limpiar - dejar que expire por timeout natural

def validate_scan_params(data):
    """Valida parámetros según context.txt"""
    errors = []
    
    # Validar DPI
    try:
        dpi = int(data.get('dpi', DEFAULT_DPI))
    except (ValueError, TypeError):
        errors.append("DPI debe ser un número entero.")
    else:
        if dpi not in ALLOWED_DPI:
            errors.append(f"DPI inválido. Debe ser uno de: {ALLOWED_DPI}")
        if dpi < 100 or dpi > 600:
            errors.append("DPI debe estar entre 100 y 600.")
    
    # Validar modo de color
    color_mode = data.get('color_mode', DEFAULT_COLOR_MODE)
    if color_mode not in SCAN_MODES:
        errors.append(f"Modo de escaneo inválido. Debe ser uno de: {SCAN_MODES}")
    
    # Validar tamaño de página
    page_size = data.get('page_size', DEFAULT_PAGE_SIZE)
    if page_size not in PAGE_SIZES:
        errors.append(f"Tamaño de página inválido. Debe ser uno de: {list(PAGE_SIZES.keys())}")
    
    # Validar rotación
    rotation = data.get('rotation', DEFAULT_ROTATION)
    if rotation not in ROTATIONS:
        errors.append(f"Rotación inválida. Debe ser una de: {ROTATIONS}")
    
    # Validar feeder (booleano) - rechazar cualquier tipo que no sea bool
    if 'feeder' in data:
        feeder = data.get('feeder')
        if feeder is None or not isinstance(feeder, bool):
            errors.append("feeder debe ser un booleano (true o false).")
    
    # Validar duplex (booleano) - rechazar cualquier tipo que no sea bool
    if 'duplex' in data:
        duplex = data.get('duplex')
        if duplex is None or not isinstance(duplex, bool):
            errors.append("duplex debe ser un booleano (true o false).")
    
    # Validar skip_blank_pages (booleano) - rechazar cualquier tipo que no sea bool
    if 'skip_blank_pages' in data:
        skip_blank = data.get('skip_blank_pages')
        if skip_blank is None or not isinstance(skip_blank, bool):
            errors.append("skip_blank_pages debe ser un booleano (true o false).")

    # Validar scanner_name (opcional)
    if 'scanner_name' in data:
        scanner_name = data.get('scanner_name')
        if scanner_name is None or not isinstance(scanner_name, str) or not scanner_name.strip():
            errors.append("scanner_name debe ser un string no vacío.")

    # Validar allow_fallback (opcional)
    if 'allow_fallback' in data:
        allow_fallback = data.get('allow_fallback')
        if allow_fallback is None or not isinstance(allow_fallback, bool):
            errors.append("allow_fallback debe ser un booleano (true o false).")

    return errors

def perform_cleanup(force=False): #force es para forzar limpieza incluso si hay escaneo activo
    """
    Ejecuta la limpieza de sesiones residuales.

    - force=True: limpieza manual forzada.
    - force=False: limpieza segura (no toca sesión en escaneo activo y solo elimina expiradas/inactivas).
    """
    cleaned_sessions = []
    skipped_sessions = []
    timeout_minutes = settings.cleanup_session_timeout_minutes

    with state_lock:
        current_scan_session_id = scan_state['session_id']
        is_currently_scanning = scan_state['is_scanning']

    lock_session = session_manager._get_active_session()
    lock_session_id = lock_session.get('session_id') if lock_session else None
    lock_expired = session_manager._is_session_expired(lock_session) if lock_session else False

    # Manejo del lock de sesión activa del sistema
    if lock_session_id:
        same_as_scanning_session = is_currently_scanning and current_scan_session_id == lock_session_id

        if force:
            try:
                session_manager.release_lock(lock_session_id)
                cleaned_sessions.append(f"lock:{lock_session_id}")
            except Exception as e:
                logger.warning(f"No se pudo liberar lock de sesión {lock_session_id}: {e}")

            if current_scan_session_id == lock_session_id:
                reset_scan_state()
        else:
            if same_as_scanning_session:
                skipped_sessions.append(f"lock:{lock_session_id}:scanning")
            elif lock_expired:
                try:
                    session_manager.release_lock(lock_session_id)
                    cleaned_sessions.append(f"lock:{lock_session_id}")
                except Exception as e:
                    logger.warning(f"No se pudo liberar lock expirado {lock_session_id}: {e}")
            else:
                skipped_sessions.append(f"lock:{lock_session_id}:not_expired")

    # Revisar todas las carpetas de sesión en SCAN_FOLDER
    if not os.path.isdir(SCAN_FOLDER):
        logger.info(f"[AUTO-CLEANUP] Carpeta de escaneo '{SCAN_FOLDER}' no existe. Nada que limpiar.")
        return

    for session_dir in os.listdir(SCAN_FOLDER):
        if not session_dir.startswith('session_'):
            continue

        session_path = os.path.join(SCAN_FOLDER, session_dir)
        if not os.path.isdir(session_path):
            continue

        folder_uuid = session_dir.replace('session_', '')
        is_scanning_folder = is_currently_scanning and current_scan_session_id == folder_uuid

        if not force and is_scanning_folder:
            skipped_sessions.append(f"folder:{session_dir}:scanning")
            continue

        should_delete = False

        if force:
            should_delete = True
        elif lock_session_id and folder_uuid == lock_session_id:
            # Si la carpeta corresponde al lock actual, solo eliminarla si la sesión expiró.
            should_delete = lock_expired and not is_scanning_folder
        else:
            folder_mtime = datetime.fromtimestamp(os.path.getmtime(session_path))
            elapsed_minutes = (datetime.now() - folder_mtime).total_seconds() / 60
            should_delete = elapsed_minutes > timeout_minutes

        if should_delete:
            try:
                shutil.rmtree(session_path)
                cleaned_sessions.append(f"folder:{session_dir}")
                logger.info(f"[AUTO-CLEANUP] Carpeta eliminada: {session_path}")
            except Exception as e:
                logger.warning(f"No se pudo borrar carpeta residual {session_path}: {e}")
        else:
            skipped_sessions.append(f"folder:{session_dir}:not_expired")

    logger.info(f"[AUTO-CLEANUP] Sesiones eliminadas: {cleaned_sessions}, omitidas: {skipped_sessions}")

# HELPERS (después de state_lock, antes de reset_scan_state)
def is_scanner_timeout(status):
    """Valida si una respuesta del escáner indica timeout."""
    return isinstance(status, dict) and status.get('timeout', False)

def is_scanner_available(status):
    """Valida si el escáner está disponible según la respuesta."""
    return isinstance(status, dict) and status.get('success', False)

@scan_bp.route('/run-cleanup', methods=['POST'])
def run_cleanup_manual():
    """
    Ejecuta limpieza manual del conector (forzada). 
    Tener en cuenta que este continua borrando si el asi haya un escaneo activo 
    y tambien sin importar si hay conexion o no con el escaner
    ---
    tags:
      - Mantenimiento
    summary: Limpieza manual de sesiones y recursos temporales
    description: |
      Inicia la limpieza del sistema de escaneo sin importar el estado actual.
      Registra advertencias si hay escaneo activo o si el escáner no responde,
      pero siempre ejecuta el proceso de limpieza.
    responses:
      200:
        description: Limpieza iniciada correctamente.
        examples:
          application/json: { "success": true, "message": "Limpieza iniciada manualmente (logs de estado incluidos)" }
    """
    # --- Revisar estado del escaneo ---
    with state_lock:
        if scan_state['is_scanning']:
            logger.warning(f" Hay un escaneo activo en sesión {scan_state['session_id']} antes de cleanup.")

    # --- Revisar conexión con escáner ---
    try:
        feeder_status = check_feeder()

        if is_scanner_timeout(feeder_status):
            logger.warning(" Timeout verificando escáner antes de cleanup.")
        elif not feeder_status.get('success', False):
            logger.warning(" ADF no disponible antes de cleanup.")
        else:
            logger.info(" Escáner conectado y listo antes de cleanup.")
    except Exception as e:
        logger.exception(f" Error al verificar escáner antes de cleanup: {e}")

    perform_cleanup(force=True)
    return jsonify({'success': True, 'message': 'Limpieza completada correctamente'}), 200

# Lock global para proteger acceso al hardware TWAIN
_hardware_lock = threading.Lock()
_zombie_threads = 0 

@scan_bp.route('/check-scanner', methods=['GET'])
def check_scanner_connection():
    """
        Verifica la conexión REAL con el escáner (hardware físico).
        ---
        tags:
            - conexión
        summary: Comprueba si el escáner está encendido y disponible
        description: |
            Realiza una verificación ligera del hardware usando check_feeder
            con timeout de 7 segundos. NO verifica ADF ni escanea páginas completas.

            Esta verificación SÍ detecta:
            - Escáner con conexión → status 200
            - Escáner desconectado/apagado (cable/wifi) → Error 504
            - Driver bloqueado → Error 503

            Esta verificación NO valida:
            - Si hay papel en ADF (eso es responsabilidad de /check-feeder)
            - Si hay hoja en cristal (eso es /check-flatbed)

            Si el timeout se activa (7s), significa problema de conexión física.

        parameters:
            - in: query
                name: scanner_name
                required: false
                schema:
                    type: string
                description: Nombre exacto del escáner TWAIN a verificar. Si no se envía, usa configuración primaria.
            - in: query
                name: allow_fallback
                required: false
                schema:
                    type: boolean
                    default: true
                description: Si es true permite intentar escáner secundario; si es false opera en modo estricto.

        responses:
            200:
                description: Escáner conectado y respondiendo (puede estar sin papel).
                examples:
                    application/json: {
                        "success": true,
                        "message": "Escáner conectado y listo",
                        "hardware_connected": true,
                        "adf_status": "ready"
                    }
            503:
                description: Escáner no disponible o desconectado.
            504:
                description: Tiempo de conexión agotado (escáner apagado o sin red).
    """
    try:
        requested_scanner = request.args.get('scanner_name', type=str)
        if isinstance(requested_scanner, str):
            requested_scanner = requested_scanner.strip() or None

        allow_fallback_param = request.args.get('allow_fallback')
        allow_fallback = settings.scanner_auto_fallback
        if allow_fallback_param is not None:
            normalized = allow_fallback_param.strip().lower()
            if normalized in ('true', '1', 'yes', 'y'):
                allow_fallback = True
            elif normalized in ('false', '0', 'no', 'n'):
                allow_fallback = False
            else:
                return jsonify({
                    'success': False,
                    'error': 'allow_fallback inválido. Use true o false.'
                }), 400

        # Verificación REAL del hardware con timeout corto (7s)
        # Usamos check_feeder porque es más rápido que check_flatbed_sheet
        # y nos da certeza de que el hardware responde
        logger.debug("[CHECK-SCANNER] Verificando conexión física del escáner...")
        
        status = check_feeder(scanner_name=requested_scanner, allow_fallback=allow_fallback)
        selected_scanner = status.get('scanner_name') if isinstance(status, dict) else None
        attempted_scanners = status.get('attempted_scanners', []) if isinstance(status, dict) else []
        
        # Caso 1: Timeout (escáner apagado, desconectado o sin red)
        if is_scanner_timeout(status):
            logger.warning("[CHECK-SCANNER] Timeout al verificar escáner")
            return jsonify({
                'success': False,
                'message': 'Tiempo agotado al verificar escáner. Verifique que esté encendido y conectado.',
                'timeout': True,
                "hardware_connected": False,
                'requested_scanner': requested_scanner,
                'selected_scanner': selected_scanner,
                'attempted_scanners': attempted_scanners
            }), 504
            
        error_msg = status.get('message', '').lower()
        
        # Patrones que indican problemas de CONEXIÓN (503)
        connection_errors = [
            'twain',  # Errores del driver TWAIN
            'no se pudo inicializar',
            'está siendo utilizado',
            'no se encontraron escáneres',
            'no disponible',
            'error al abrir',
            'no responde'
        ]
        
        # Patrones que indican el escáner está conectado pero sin papel (200)
        operational_warnings = [
            'No hay papel en el alimentador',
            'no hay papel',
            'alimentador vacío',
            'feeder vacío',
            'sin hojas'
        ]
        
        # Verificar si es error de conexión real
        is_connection_error = any(pattern in error_msg for pattern in connection_errors)
        is_operational_warning = any(pattern in error_msg for pattern in operational_warnings)
        
        # Caso 2a: Error de conexión física (503)
        if not status.get('success', False) and is_connection_error:
            logger.warning(f"[CHECK-SCANNER] Error de conexión: {status.get('message')}")
            return jsonify({
                'success': False,
                'error': status.get('message', 'Escáner no disponible'),
                'hardware_connected': False,
                'connection_error': True,
                'requested_scanner': requested_scanner,
                'selected_scanner': selected_scanner,
                'attempted_scanners': attempted_scanners
            }), 503
        
        # Caso 2b: Escáner conectado pero sin papel (200 con advertencia)
        if not status.get('success', False) and is_operational_warning:
            logger.info(f"[CHECK-SCANNER] Escáner conectado pero ADF vacío")
            return jsonify({
                'success': True,
                'message': 'Escáner conectado y disponible',
                'hardware_connected': True,
                'adf_status': 'vacio',
                'warning': status.get('message'),
                'requested_scanner': requested_scanner,
                'selected_scanner': selected_scanner,
                'attempted_scanners': attempted_scanners
            }), 200
        
        # Caso 2c: Otro tipo de error no clasificado (tratar como conexión por seguridad)
        if not status.get('success', False):
            logger.warning(f"[CHECK-SCANNER] Error no clasificado: {status.get('message')}")
            return jsonify({
                'success': False,
                'error': status.get('message', 'Error desconocido al verificar escáner'),
                'hardware_connected': False,
                'requested_scanner': requested_scanner,
                'selected_scanner': selected_scanner,
                'attempted_scanners': attempted_scanners
            }), 503
        
        # Caso 3: Éxito - Escáner responde correctamente Y hay papel
        logger.debug("[CHECK-SCANNER] Escáner disponible y ADF con papel")
        return jsonify({
            'success': True,
            'message': 'Escáner conectado y disponible',
            'hardware_connected': True,
            'adf_status': 'ready',
            'requested_scanner': requested_scanner,
            'selected_scanner': selected_scanner,
            'attempted_scanners': attempted_scanners
        }), 200

    except Exception as e:
        logger.exception("[CHECK-SCANNER] Error inesperado")
        return jsonify({
            'success': False,
            'message': f'Error al verificar escáner: {str(e)}',
            'hardware_connected': False,
            'requested_scanner': requested_scanner if 'requested_scanner' in locals() else None
        }), 500

# HELPER para limpieza en fallos de inicio de sesión
def _cleanup_failed_session(session_id, file_manager):
    """Limpia recursos cuando falla el inicio de sesión."""
    try:
        file_manager.cleanup_session()
    except Exception as e:
        logger.warning(f"Error al limpiar sesión {session_id}: {e}")
    
    try:
        session_manager.release_lock(session_id)
    except Exception as e:
        logger.warning(f"Error al liberar lock de {session_id}: {e}")
    
    reset_scan_state()

# HELPER para verificar disponibilidad del escáner
def _verify_scanner_availability(feeder_mode, scanner_name=None, allow_fallback=True):
    """
    Verifica disponibilidad del escáner según el modo (ADF o Cristal).
    
    Args:
        feeder_mode (bool): True para ADF, False para Cristal
    
    Returns:
        tuple: (success: bool, error_response: dict|None, status_code: int|None)
               - success=True, None, None si el escáner está disponible
               - success=False, error_dict, 504 si hay timeout
               - success=False, error_dict, 400 si no hay hoja/papel
    """
    # timeout = FEEDER_TIMEOUT if feeder_mode else FLATBED_TIMEOUT
    # func = check_feeder if feeder_mode else check_flatbed_sheet
    func = check_feeder if feeder_mode else check_flatbed_sheet
    status = func(scanner_name=scanner_name, allow_fallback=allow_fallback)
    
    if is_scanner_timeout(status):
        return False, {'success': False, 'error': status.get('message')}, 504, status.get('scanner_name')
    
    if not is_scanner_available(status):
        return False, {'success': False, 'error': status.get('message')}, 400, status.get('scanner_name')
    
    return True, None, None, status.get('scanner_name')

@scan_bp.route('/start', methods=['POST'])
def start_scan():
    """
    Inicia una nueva sesión de escaneo (ADF o Cristal).
    ---
    tags:
      - Escanear
    description: |
      Crea sesión, verifica disponibilidad del escáner y aplica parámetros.
      Para ADF: inicia thread en background.
      Para Cristal: escanea inmediatamente y retorna resultado.

    parameters:
      - in: body
        name: body
        schema:
          type: object
          properties:
            user_id:
              type: string
              default: "anonymous"
              example: "usuario1"
              description: ID del usuario que inicia el escaneo.
            dpi:
              type: integer
              default: 300
              example: 300
              description: Resolución del escaneo en DPI ("300", "400","600").
            color_mode:
              type: string
              default: "Text"
              example: "Text"
              description: Modo de color ( "Text", "Text/Photo", "Gray", "Color").
            duplex:
              type: boolean
              default: false
              example: false
              description: true si es Escaneo a doble cara, false si es escaneo a una sola cara.
            feeder:
              type: boolean
              default: false
              example: false
              description: true si se usa alimentador automático (ADF), false si se usa cristal (flatbed).
            page_size:
              type: string
              default: "LT-R"
              example: "LT-R"
              description: Tamaño de la hoja ("LT-R", "A4-R", "13-LG", "A5-R").
            rotation:
              type: string
              default: "auto"
              example: "off"
              description: Rotación de la página en grados ("off", "right90", "180", "left90", "auto").
            skip_blank_pages:
              type: boolean
              default: true
              example: true
              description: Indica si se deben omitir páginas en blanco durante el escaneo. Si es true, las páginas en blanco no se guardan y recordar que el escaneo siempre se detiene al encontrar 3 paginas consecutivas en blanco.
    responses:
      200:
        description: Escaneo iniciado correctamente.
        examples:
          application/json: { "success": true, "session_id": "12345", "message": "Escaneo iniciado correctamente", "scan_params": {} }
      400:
        description: Error en los parámetros de entrada o en la comprobación de hojas.
        examples:
          application/json: { "success": false, "error": "ADF no disponible" }
      409:
        description: Ya existe un escaneo en progreso o no se pudo adquirir lock.
        examples:
          application/json: { "success": false, "error": "Ya hay un escaneo en progreso" }
      504:
        description: Tiempo agotado al comprobar ADF o cristal.
        examples:
          application/json: { "success": false, "error": "Tiempo agotado al comprobar ADF. Verifique el escáner." }
    """
    data = request.get_json() or {}
    user_id = data.get('user_id', 'anonymous')
    requested_scanner = data.get('scanner_name')
    if isinstance(requested_scanner, str):
        requested_scanner = requested_scanner.strip() or None
    allow_fallback = data.get('allow_fallback', settings.scanner_auto_fallback)

    # 1. Validar parametros
    validation_errors = validate_scan_params(data) # Validar parámetros, en caso de error retorna lista de errores
    if validation_errors:
        return jsonify({'success': False, 'errors': validation_errors}), 400

    # 2. Verificar que no haya escaneo activo + crear recursos ATÓMICAMENTE
    with state_lock:
        if scan_state['is_scanning']:
            return jsonify({
                'success': False,
                'error': 'Ya hay un escaneo en progreso',
            }), 409

        # Crear sesión y carpeta
        lock_result = session_manager.acquire_lock(
            user_id,
            timeout_minutes=settings.cleanup_session_timeout_minutes,
            scanner_name=requested_scanner
        )
        if not lock_result['success']:
            return jsonify({'success': False, 'error': lock_result['message']}), 409

        session_id = lock_result['session_id']
        file_manager = ScanFileManager(session_id)

        scan_state.update({
            'is_scanning': True,
            'session_id': session_id,
            'user_id': user_id,
            'scanner_name': None,
            'file_manager': file_manager,
            'progress': {
                'status': 'ready',
                'message': 'Sesión iniciada, listo para escanear',
                'pages_scanned': 0,
                'batch_active': True
            }
        })

    # Parámetros de escaneo
    scan_params = {
        'dpi': data.get('dpi', DEFAULT_DPI),
        'color_mode': data.get('color_mode', DEFAULT_COLOR_MODE),
        'duplex': data.get('duplex', DEFAULT_DUPLEX),
        'feeder': data.get('feeder', DEFAULT_FEEDER),
        'page_size': data.get('page_size', DEFAULT_PAGE_SIZE),
        'rotation': data.get('rotation', DEFAULT_ROTATION),
        'skip_blank_pages': data.get('skip_blank_pages', DEFAULT_SKIP_BLANK_PAGES),
        'scanner_name': requested_scanner,
    }
    
    if scan_params['feeder']:
        # ADF: flujo normal de verificación
        success, error_response, status_code, selected_scanner = _verify_scanner_availability(
            True,
            scanner_name=requested_scanner,
            allow_fallback=allow_fallback
        )
        if not success:
            _cleanup_failed_session(session_id, file_manager)
            return jsonify(error_response), status_code

        with state_lock:
            if scan_state['session_id'] == session_id:
                scan_state['scanner_name'] = selected_scanner

        session_manager.update_session_scanner(selected_scanner, session_id)

        scan_params['scanner_name'] = selected_scanner

        # INICIAR ESCANEO EN BACKGROUND
        thread = threading.Thread(
            target=_perform_scan,
            args=(session_id, file_manager, scan_params),
            daemon=True
        )
        thread.start()

        return jsonify({
            'success': True,
            'session_id': session_id,
            'message': 'Escaneo desde ADF iniciado correctamente',
            'scanner_name': selected_scanner,
            'selected_scanner': selected_scanner,
            'scan_params': scan_params
        }), 200
    
    else:
        # FLATBED (cristal): flujo optimizado (escanear + guardar directamente)
        result = validate_and_scan_flatbed(
            session_id=session_id,
            file_manager=file_manager,
            dpi=scan_params['dpi'],
            color_mode=scan_params['color_mode'],
            page_size=scan_params['page_size'],
            rotation=scan_params['rotation'],
            scanner_name=requested_scanner,
            allow_fallback=allow_fallback
        )

        selected_scanner = result.get('scanner_name')
        
        # Manejar resultado
        if result.get('timeout'):
            _cleanup_failed_session(session_id, file_manager)
            return jsonify({
                'success': False,
                'error': result.get('message', 'Tiempo agotado al verificar cristal'),
                'timeout': True
            }), 504

        if result.get('blank_page'):
            # Hoja en blanco: borrar sesión y carpeta
            _cleanup_failed_session(session_id, file_manager)
            return jsonify({
                'success': False,
                'error': 'Hoja en blanco detectada o no hay hoja. Coloque documento válido.'
            }), 400

        if not result['success']:
            _cleanup_failed_session(session_id, file_manager)
            return jsonify({
                'success': False,
                'error': result.get('message', 'Error al escanear')
            }), 400
            
        if scan_params['rotation'] == 'auto':
            # Auto-rotar imagen escaneada
            page_path = os.path.join(file_manager.session_folder, result['filename'])
            rotation_result = auto_rotate_image(page_path)

            if rotation_result.get('rotated'):
                logger.info(f"✅ Página rotada {rotation_result['angle']}° en cristal")

        # Éxito: actualizar estado y retornar
        with state_lock:
            scan_state['scanner_name'] = selected_scanner
            scan_state['progress'].update({
                'status': 'completed',
                'pages_scanned': 1,
                'message': result['message']
            })

        session_manager.update_session_scanner(selected_scanner, session_id)
    
        # NO iniciar thread porque ya terminamos
        return jsonify({
            'success': True,
            'session_id': session_id,
            'message': 'Escaneo desde cristal completado',
            'scanner_name': selected_scanner,
            'selected_scanner': selected_scanner,
            'scan_params': scan_params
        }), 200

@scan_bp.route('/continue', methods=['POST'])
def continue_scan():
    """
    Permite continuar escaneando dentro de la misma sesión activa. Funciona para Flatbed (cristal) y feeder/ADF (bandeja).
    ---
    tags:
      - Escanear
    description: |
      Valida session_id/user_id y continúa escaneando.
      Para ADF: inicia thread en background.
      Para Cristal: escanea inmediatamente.
      NO finaliza sesión en caso de error (mantiene sesión abierta).
      Parametro opcional: last_page_number:
          type: integer
          default: 5
          description: (Opcional) Último número de página conocido por Django. Permite sincronizar el contador cuando se eliminan, reordenan o suben páginas manualmente desde el frontend. La siguiente página se guardará como last_page_number + 1.

    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - session_id
            - user_id
          properties:
            session_id:
              type: string
              example: "12345"
              description: Identificador de la sesión de escaneo que se encuentra activa.
            user_id:
              type: string
              example: "usuario1"
              description: ID del usuario que inicia el escaneo.
            dpi:
              type: integer
              default: 300
              example: 300
              description: Resolución del escaneo en DPI ("300", "400","600").
            color_mode:
              type: string
              default: "Text"
              example: "Text"
              description: Modo de color ( "Text", "Text/Photo", "Gray", "Color").
            duplex:
              type: boolean
              default: false
              example: false
              description: true si es Escaneo a doble cara, false si es escaneo a una sola cara.
            feeder:
              type: boolean
              default: false
              example: false
              description: true si se usa alimentador automático (ADF), false si se usa cristal (flatbed).
            page_size:
              type: string
              default: "LT-R"
              example: "LT-R"
              description: Tamaño de la hoja ("LT-R", "A4-R", "13-LG", "A5-R").
            rotation:
              type: string
              default: "auto"
              example: "off"
              description: Rotación de la página en grados ("off", "right90", "180", "left90", "auto").
            skip_blank_pages:
              type: boolean
              default: true
              example: true
              description: Indica si se deben omitir páginas en blanco durante el escaneo. Si es true, las páginas en blanco no se guardan y recordar que el escaneo siempre se detiene al encontrar 3 paginas consecutivas en blanco.
    responses:
      200:
        description: Escaneo continuado correctamente. Monitorear progreso en tiempo real con /status.
        examples:
          application/json: { "success": true, "message": "Escaneo continuado correctamente.", "session_id": "12345", "user_id": "usuario1", "scan_params": {} }
      400:
        description: Error en los parámetros de entrada, no hay sesión activa o no hay hoja.
        examples:
          application/json: { "success": false, "error": "Se requiere user_id para continuar escaneando." }
      403:
        description: Usuario o session_id no coinciden con la sesión activa o bloqueada.
        examples:
          application/json: { "success": false, "error": "El session_id proporcionado no coincide con la sesión activa." }
      404:
        description: No hay sesión activa en el sistema de bloqueo.
        examples:
          application/json: { "success": false, "error": "No hay sesión activa en el sistema de bloqueo." }
      409:
        description: No se puede continuar debido a que el estado actual del escaneo no lo permite.
        examples:
          application/json: { "success": false, "error": "No se puede continuar. Estado actual: scanning." }
      504:
        description: Tiempo agotado al verificar disponibilidad de ADF o cristal.
        examples:
          application/json: { "success": false, "error": "Tiempo agotado al comprobar ADF. Verifique el escáner." }
    """
    data = request.get_json() or {}
    user_id = data.get('user_id')
    requested_session_id = data.get('session_id')
    last_page_number = data.get('last_page_number')  # Sincronización con Django
    requested_scanner = data.get('scanner_name')
    if isinstance(requested_scanner, str):
        requested_scanner = requested_scanner.strip() or None
    request_allow_fallback = data.get('allow_fallback', settings.scanner_auto_fallback)
    
    # Validar que se proporcione user_id
    if not user_id:
        return jsonify({
            'success': False,
            'error': 'Se requiere user_id para continuar escaneando.'
        }), 400
    
    # Validar que se proporcione session_id
    if not requested_session_id:
        return jsonify({
            'success': False,
            'error': 'Se requiere session_id para continuar escaneando.'
        }), 400
    
    with state_lock:
        # Verificar que hay sesión activa en memoria
        if not scan_state['is_scanning'] or not scan_state['session_id']:
            return jsonify({
                'success': False,
                'error': 'No hay sesión activa para continuar escaneando.'
            }), 400
        
        # Verificar que el session_id del request coincida con el de memoria
        if scan_state['session_id'] != requested_session_id:
            return jsonify({
                'success': False,
                'error': f'El session_id proporcionado: {requested_session_id} no coincide con la sesión activa.'
            }), 403
            
        # Verificar que el user_id coincida
        if scan_state['user_id'] != user_id:
            return jsonify({
                'success': False,
                'error': f'El usuario "{user_id}" no tiene permiso para continuar esta sesión'
            }), 403
        
        # También validar archivo dentro del lock
        active_session = session_manager._get_active_session()
        if not active_session:
            return jsonify({'success': False, 'error': 'No hay sesión bloqueada'}), 404

        # Verificar que el session_id coincida con session.lock
        if active_session.get('session_id') != requested_session_id:
            return jsonify({
                'success': False,
                'error': f'El session_id no coincide con la sesión bloqueada'
            }), 403
            
        # Verificar que el user_id coincida con session.lock
        if active_session.get('user_id') != user_id:
            return jsonify({
                'success': False,
                'error': f'El user_id no coincide con la sesión bloqueada'
            }), 403
            
        # Verificar que el progreso esté en estado válido para continuar
        current_status = scan_state['progress']['status']
        if current_status not in ['completed', 'waiting', 'ready']:
            return jsonify({
                'success': False,
                'error': f'No se puede continuar. Estado actual: {current_status}. Espere a que termine el escaneo actual.'
            }), 409
            
        # MARCAR como 'scanning' ANTES de salir del lock
        scan_state['progress'].update({
            'status': 'scanning',
            'message': 'Preparando escaneo...',
            'error': None
        })
        
        session_id = scan_state['session_id']
        session_scanner = scan_state.get('scanner_name')

        # Evitar cambio silencioso de escáner dentro de una sesión ya fijada.
        if session_scanner and requested_scanner and requested_scanner != session_scanner:
            return jsonify({
                'success': False,
                'error': (
                    f'No se permite cambiar escáner en sesión activa. '
                    f'Escáner de sesión: {session_scanner}, solicitado: {requested_scanner}.'
                )
            }), 409

        file_manager = scan_state['file_manager']
        
        # Sincronizar contador de páginas si Django lo envía
        # Útil cuando Django elimina/reordena páginas o sube imágenes manualmente
        if last_page_number is not None:
            try:
                new_counter = int(last_page_number) + 1
                file_manager.set_page_counter(new_counter)
                logger.info(f"[CONTINUE] Contador de páginas sincronizado a {new_counter}")
            except (ValueError, TypeError) as e:
                logger.warning(f"[CONTINUE] No se pudo actualizar contador de páginas: {e}")

        # Asegurar que el file_manager global tenga el contador actualizado antes de escanear
        scan_state['file_manager'] = file_manager
        
        # Validar parámetros de escaneo
        validation_errors = validate_scan_params(data)
        if validation_errors:
            with state_lock:
                scan_state['progress']['status'] = 'waiting'
            return jsonify({'success': False, 'errors': validation_errors}), 400

    scan_params = {
        'dpi': data.get('dpi', DEFAULT_DPI),
        'color_mode': data.get('color_mode', DEFAULT_COLOR_MODE),
        'duplex': data.get('duplex', DEFAULT_DUPLEX),
        'feeder': data.get('feeder', DEFAULT_FEEDER),
        'page_size': data.get('page_size', DEFAULT_PAGE_SIZE),
        'rotation': data.get('rotation', DEFAULT_ROTATION),
        'skip_blank_pages': data.get('skip_blank_pages', DEFAULT_SKIP_BLANK_PAGES),
        'scanner_name': session_scanner or requested_scanner,
    }

    allow_fallback = bool(request_allow_fallback) if not session_scanner else False
    
    if scan_params['feeder']:
        # ADF: flujo normal
        success, error_response, status_code, selected_scanner = _verify_scanner_availability(
            True,
            scanner_name=scan_params['scanner_name'],
            allow_fallback=allow_fallback
        )
        if not success:
            with state_lock:
                if scan_state['session_id'] == requested_session_id:
                    scan_state['progress']['status'] = 'waiting'
            return jsonify(error_response), status_code

        scan_params['scanner_name'] = selected_scanner
        with state_lock:
            if scan_state['session_id'] == requested_session_id:
                scan_state['scanner_name'] = selected_scanner

        session_manager.update_session_scanner(selected_scanner, requested_session_id)

        # INICIAR ESCANEO EN BACKGROUND, asegurando que el file_manager tenga el contador correcto
        # Se pasa el file_manager ya sincronizado
        thread = threading.Thread(
            target=_perform_scan,
            args=(session_id, file_manager, scan_params),
            daemon=True
        )
        thread.start()

        return jsonify({
            'success': True,
            'message': 'Escaneo desde ADF continuado correctamente',
            'session_id': session_id,
            'scanner_name': selected_scanner,
            'selected_scanner': selected_scanner,
        }), 200
        
    else:
        # FLATBED: flujo optimizado
        result = validate_and_scan_flatbed(
            session_id=session_id,
            file_manager=file_manager,
            dpi=scan_params['dpi'],
            color_mode=scan_params['color_mode'],
            page_size=scan_params['page_size'],
            rotation=scan_params['rotation'],
            scanner_name=scan_params['scanner_name'],
            allow_fallback=allow_fallback
        )

        selected_scanner = result.get('scanner_name') or scan_params['scanner_name']
        
        if result.get('timeout'):
            with state_lock:
                scan_state['progress']['status'] = 'waiting'
            return jsonify({
                'success': False,
                'error': 'Tiempo agotado al verificar cristal'
            }), 504

        if result.get('blank_page'):
            # NO borrar sesión en /continue, solo advertir
            with state_lock:
                scan_state['progress'].update({
                    'status': 'waiting',
                    'message': 'Hoja en blanco detectada. Coloque otra hoja para continuar.'
                })
            return jsonify({
                'success': False,
                'error': 'Hoja en blanco. Sesión activa, puede continuar con otra hoja.',
                'keep_session': True
            }), 400

        if not result['success']:
            with state_lock:
                scan_state['progress']['status'] = 'waiting'
            return jsonify({
                'success': False,
                'error': result.get('message', 'Error al escanear')
            }), 400
            
        # APLICAR AUTO-ROTACIÓN si está habilitada
        if scan_params['rotation'] == 'auto':
            page_path = os.path.join(file_manager.session_folder, result['filename'])
            rotation_result = auto_rotate_image(page_path)

            if rotation_result.get('rotated'):
                logger.info(f"✅ Página rotada {rotation_result['angle']}° en cristal")
            elif rotation_result.get('error'):
                logger.warning(f"⚠️ Error en auto-rotación: {rotation_result['error']}")
            else:
                logger.debug(f"ℹ️ Auto-rotación no aplicada: {rotation_result.get('reason', 'desconocido')}")

        # Éxito
        with state_lock:
            scan_state['scanner_name'] = selected_scanner
            scan_state['progress'].update({
                'status': 'completed',
                'pages_scanned': file_manager.get_page_count(),
                'message': result['message']
            })

        session_manager.update_session_scanner(selected_scanner, requested_session_id)

        return jsonify({
            'success': True,
            'message': 'Página escaneada en cristal correctamente',
            'session_id': session_id,
            'scanner_name': selected_scanner,
            'selected_scanner': selected_scanner,
        }), 200
        
def _perform_scan(session_id, file_manager, scan_params):
    """
    Ejecuta escaneo en segundo plano (thread daemon).
    
    Flujo:
        1. Ejecuta scan_document() con TWAIN
        2. Si rotation='auto': aplica auto_rotate_image() a páginas nuevas
        3. Actualiza scan_state['progress'] en tiempo real
        4. Si error + carpeta vacía: limpia carpeta automáticamente
    
    Args:
        session_id (str): UUID de sesión activa
        file_manager (ScanFileManager): Gestor de archivos de la sesión
        scan_params (dict): Parámetros de escaneo (dpi, color_mode, rotation, etc.)
    
    Returns:
        None (actualiza scan_state directamente)
    
    Note:
        - Thread-safe mediante state_lock
        - Si la sesión se cancela durante escaneo, termina silenciosamente
        - En modo ADF: scan_document() guarda automáticamente las imágenes
        - En modo Flatbed: scan_document() retorna rutas (ya guardadas)
    """
    try:
        # Iniciar escaneo
        with state_lock:
            if scan_state['session_id'] != session_id:
                logger.warning(f"Sesión {session_id} cancelada durante escaneo")
                return
            scan_state['progress'].update({
                'status': 'scanning',
                'message': 'Escaneando documentos...',
                'pages_scanned': 0,
                'error': None
            })
        
        pages_before = file_manager.get_page_count()
        
        twain_rotation = scan_params['rotation']
        if twain_rotation == 'auto':
            twain_rotation = 'off'  # TWAIN no rota, lo haremos después

        # Ejecutar escaneo TWAIN
        images = scan_document(
            dpi=scan_params['dpi'],
            color_mode=scan_params['color_mode'],
            duplex=scan_params['duplex'],
            feeder=scan_params['feeder'],
            page_size=scan_params['page_size'],
            rotation=twain_rotation,
            skip_blank_pages=scan_params['skip_blank_pages'],
            session_id=session_id,
            scanner_name=scan_params.get('scanner_name'),
            allow_fallback=False,
            file_manager=file_manager  # Pasar el file_manager sincronizado
        )

        if scan_params['rotation'] == 'auto':
            logger.info("Iniciando auto-rotación de páginas escaneadas...")
            all_pages = file_manager.get_scanned_pages()
            
            new_pages = []
            for p in all_pages:
                try:
                    # Extraer número de página del formato "page_N.ext"
                    name = os.path.splitext(p['filename'])[0]
                    if not name.startswith("page_"):
                        raise ValueError("Formato de filename inesperado")
                    page_num = int(name.split("_", 1)[1])
                    if page_num > pages_before:
                        new_pages.append(p)
                except (IndexError, ValueError) as e:
                    logger.warning(f"Formato de filename inesperado: {p['filename']}")
                    continue

            if not new_pages:
                logger.warning("No se encontraron páginas nuevas para auto-rotar.")

            rotated_count = 0
            failed_auto = 0
            skipped_blank = 0

            for page in new_pages:
                # Verificar cancelación antes de cada rotación
                with state_lock:
                    if scan_state['session_id'] != session_id:
                        logger.info(f"⚠️ Auto-rotación interrumpida por cancelación")
                        break
                    
                page_path = os.path.join(file_manager.session_folder, page['filename'])
                
                if not scan_params['skip_blank_pages']:
                    try:
                        from PIL import Image
                        with Image.open(page_path) as img:
                            if is_blank_page(img):
                                skipped_blank += 1
                                logger.info(f"⏭️ {page['filename']}: omitida de auto-rotación (página en blanco)")
                                continue
                    except Exception as e:
                        logger.warning(f"⚠️ Error verificando {page['filename']}: {e}")
                
                # aplicar rotación solo a páginas válidas
                result = auto_rotate_image(page_path)
                if result.get('rotated'):
                    rotated_count += 1
                    logger.info(f"✅ Página {page['filename']} rotada {result['angle']}°")
                elif result.get('reason'):
                    failed_auto += 1
                    logger.warning(f"⚠️ No se pudo determinar orientación (poco texto) en {page['filename']}")
                elif result.get('error'):
                    failed_auto += 1
                    logger.warning(f"⚠️ Error rotando {page['filename']}: {result['error']}")

            # Actualizar mensaje de progreso con resultados de auto-rotación
            if rotated_count or failed_auto:
                with state_lock:
                    if scan_state['session_id'] == session_id:
                        extra = f" ({rotated_count} auto-rotadas"
                        if skipped_blank:
                            extra += f", {skipped_blank} blancas omitidas"
                        if failed_auto:
                            extra += f", {failed_auto} sin texto)"
                        else:
                            extra += ")"
                        scan_state['progress']['message'] += extra

        if scan_params['feeder']:
            # Modo ADF: las imágenes ya fueron guardadas por scan_document
            # Solo necesitamos actualizar el progreso
            pages_count = file_manager.get_page_count()
            with state_lock:
                if scan_state['session_id'] == session_id:
                    scan_state['progress'].update({
                        'status': 'completed',
                        'message': f'Escaneo completado: {pages_count} páginas',
                        'pages_scanned': pages_count
                    })
        else:
            # Modo Flatbed: scan_document retorna rutas, no imágenes
            # Las imágenes ya fueron guardadas, solo actualizar progreso
            # Escaneo completado correctamente
            if not images:
                images = []

            with state_lock:
                if scan_state['session_id'] == session_id:
                    scan_state['progress'].update({
                        'status': 'completed',
                        'message': f'Escaneo completado: {len(images)} páginas',
                        'pages_scanned': len(images)
                    })

    except Exception as e:
        # Actualizar páginas escenadas antes de marcar error
        current_pages = file_manager.get_page_count() if file_manager else 0
        
        with state_lock:
            if scan_state['session_id'] == session_id:
                scan_state['progress'].update({
                    'status': 'error',
                    'message': f'Error en el escaneo: {str(e)}',
                    'error': str(e),
                    'pages_scanned': current_pages
                })
        logger.exception(f"[ERROR] _perform_scan en sesión {session_id}: {e}")

        # Manejo de caso específico: no hay hoja o error crítico
        if file_manager:
            try:
                # Borra solo si la carpeta está vacía
                if file_manager.get_page_count() == 0:
                    cleanup_result = file_manager.cleanup_session()
                    logger.info(f"Carpeta vacía de sesión {session_id} eliminada: {cleanup_result}")
                else:
                    logger.info(f"Carpeta de sesión {session_id} contiene imágenes, no se borrará automáticamente")
            except Exception as cleanup_error:
                logger.warning(f"No se pudo borrar carpeta de sesión {session_id}: {cleanup_error}")
    finally:
        # Mantener la sesión activa solo si no hubo error
        with state_lock:
            if scan_state['session_id'] == session_id:
                current_status = scan_state['progress']['status']
                # Solo cambiar a 'waiting' si completó (no si está en error)
                if current_status == 'completed':
                    scan_state['progress'].update({
                        'status': 'waiting',
                        'message': 'Escaneo completado. Esperando siguiente acción.'
                    })

@scan_bp.route('/status', methods=['GET'])
def get_scan_status():
    """
    Obtiene el estado actual del escaneo.
    ---
    tags:
      - Estado
    summary: Consulta el progreso y la sesión activa del escaneo
    description: |
      Retorna información sobre la sesión de escaneo activa, incluyendo progreso,
      usuario asociado y páginas escaneadas. Si no hay escaneo activo, indica el estado inactivo.
      
      El campo `page_count` permite al frontend mostrar contadores en tiempo real
      sin necesidad de parsear el array completo de páginas.
      
    responses:
      200:
        description: Estado del escaneo o mensaje de inactividad.
        examples:
          application/json:
            is_scanning: true
            session_id: "abc123"
            user_id: "user_01"
            page_count: 3
            progress:
              status: "scanning"
              pages_scanned: 3
            pages: [
                            {"filename": "page_1.webp", "size": 1024},
                            {"filename": "page_2.webp", "size": 2048}
            ]
    """
    with state_lock:
        if not scan_state['is_scanning']:
            return jsonify({
                'is_scanning': False,
                'message': 'No hay escaneo activo',
                'page_count': 0
            })
        
        # Obtener páginas escaneadas
        pages = []
        page_count = 0
        
        if scan_state['file_manager']:
            try:
                pages = scan_state['file_manager'].get_scanned_pages()
                page_count = scan_state['file_manager'].get_page_count()
            except Exception as e:
                logger.warning(f"Error obteniendo páginas escaneadas: {e}")
                pages = []
                page_count = 0
        
        return jsonify({
            'is_scanning': True,
            'session_id': scan_state['session_id'],
            'user_id': scan_state['user_id'],
            'scanner_name': scan_state.get('scanner_name'),
            'page_count': page_count,
            'progress': scan_state['progress'],
            'pages': pages
        })

@scan_bp.route('/pages', methods=['GET'])
def get_scanned_pages():
    """
    Obtiene la lista de páginas escaneadas de la sesión activa.
    ---
    tags:
      - Estado
    summary: Lista las páginas escaneadas en la sesión actual
    description: |
      Devuelve las páginas escaneadas con sus nombres de archivo y URL de descarga.
      Si no hay una sesión activa, retorna un error 404.
    responses:
      200:
        description: Páginas escaneadas encontradas.
        examples:
          application/json:
            success: true
            session_id: "abc123"
            page_count: 3
            pages:
                            - filename: "page_1.webp"
                                download_url: "http://localhost:5000/api/scan/download/abc123/page_1.webp"
      404:
        description: No hay sesión activa.
      503:
        description: Error al leer archivos de la sesión.
    """
    with state_lock:
        if not scan_state['file_manager']:
            return jsonify({
                'success': False,
                'error': 'No hay sesión activa'
            }), 404
        
        try:
            pages = scan_state['file_manager'].get_scanned_pages()
            current_session_id = scan_state['session_id']
        except Exception as e:
            logger.error(f"Error al obtener páginas de sesión activa: {e}")
            return jsonify({
                'success': False,
                'error': 'Error al leer archivos de la sesión'
            }), 503

    # Agregar URL de descarga para consumo desde Django
    base_url = request.host_url.rstrip('/')
    pages_with_urls = [
        {
            **p,
            'download_url': f"{base_url}/api/scan/download/{current_session_id}/{p['filename']}"
        }
        for p in pages
    ]
    return jsonify({
        'success': True,
        'session_id': current_session_id,
        'page_count': len(pages_with_urls),
        'pages': pages_with_urls
    })

@scan_bp.route('/pages/<session_id>', methods=['GET'])
def get_session_pages(session_id):
    """
    Obtiene las páginas escaneadas de una sesión específica.
    ---
    tags:
      - Estado
    summary: Lista las páginas escaneadas de una sesión dada
    description: |
      Permite consultar las páginas de cualquier sesión usando el session_id.
      Devuelve el nombre de cada archivo y su URL de descarga para consumo desde Django.
      Si la sesión no existe, retorna un error 404.
      
    parameters:
      - name: session_id
        in: path
        type: string
        required: true
        description: ID de la sesión a consultar (puede incluir o no el prefijo 'session_')
        
    responses:
      200:
        description: Páginas escaneadas encontradas.
        examples:
          application/json:
            success: true
            session_id: "session_abc123"
            page_count: 3
            pages:
                            - filename: "page_1.webp"
                                download_url: "http://localhost:5000/api/scan/download/session_abc123/page_1.webp"
      404:
        description: Sesión no encontrada.
      503:
        description: Error al leer archivos de la sesión.
    """
    normalized = session_id if session_id.startswith("session_") else f"session_{session_id}"
    session_path = os.path.join(SCAN_FOLDER, normalized)
    
    if not os.path.isdir(session_path):
        return jsonify({
            'success': False,
            'error': f'Sesión {normalized} no encontrada'
        }), 404
    
    file_manager = ScanFileManager(normalized)
    try:
        pages = file_manager.get_scanned_pages()
        if pages is None:
            pages = []
    except Exception as e:
        logger.error(f"Error al obtener páginas de {normalized}: {e}")
        return jsonify({
            'success': False,
            'error': 'Error al leer archivos de la sesión'
        }), 503
    
    # Agregar URL de descarga para consumo desde Django
    base_url = request.host_url.rstrip('/')
    pages_with_urls = [
        {
            **p,
            'download_url': f"{base_url}/api/scan/download/{normalized}/{p['filename']}"
        }
        for p in pages
    ]

    return jsonify({
        'success': True,
        'session_id': normalized,
        'page_count': len(pages_with_urls),
        'pages': pages_with_urls
    })

@scan_bp.route('/download/<session_id>/<filename>', methods=['GET'])
def download_page(session_id, filename):
    """
        Descarga una imagen específica de una sesión.
        ---
        tags:
            - Descarga
        summary: Obtener archivo WEBP de una sesión
        description: |
            Permite descargar un archivo específico de una sesión de escaneo.
            Django u otros clientes pueden usar esta ruta para obtener los archivos WEBP generados
            (PNG legacy si existiera por sesiones anteriores).

            Validaciones de seguridad:
            - Sanitiza filename con secure_filename()
            - Solo permite archivos .webp (y .png legacy)
            - Previene path traversal attacks

        parameters:
            - name: session_id
                in: path
                type: string
                required: true
                description: ID de la sesión (puede incluir o no el prefijo 'session_')
            - name: filename
                in: path
                type: string
                required: true
                description: Nombre del archivo a descargar (ej. "page_1.webp")
        responses:
            200:
                description: Archivo descargado correctamente
                content:
                    image/webp:
                        schema:
                            type: string
                            format: binary
            400:
                description: Validación de seguridad fallida
                examples:
                    application/json:
                        nombre_invalido:
                            value:
                                success: false
                                error: "Nombre de archivo inválido"
                        extension_invalida:
                            value:
                                success: false
                                error: "Solo se permiten archivos WEBP o PNG"
                        path_traversal:
                            value:
                                success: false
                                error: "Nombre de archivo inválido"
            404:
                description: Sesión o archivo no encontrado
                examples:
                    application/json:
                        sesion_no_existe:
                            value:
                                success: false
                                error: "Sesión no encontrada"
                        archivo_no_existe:
                            value:
                                success: false
                                error: "Archivo no encontrado"
    """

    # Validar y sanitizar filename
    safe_filename = secure_filename(filename)
    if not safe_filename:
        return jsonify({
            'success': False,
            'error': 'Nombre de archivo inválido'
        }), 400

    # Validar extensión WEBP o PNG legacy
    if not safe_filename.lower().endswith(('.webp', '.png')):
        return jsonify({
            'success': False,
            'error': 'Solo se permiten archivos WEBP o PNG'
        }), 400

    # Normalizar session_id
    normalized = session_id if session_id.startswith("session_") else f"session_{session_id}"
    session_path = os.path.join(SCAN_FOLDER, normalized)

    # Validar existencia de sesión
    if not os.path.isdir(session_path):
        return jsonify({
            'success': False,
            'error': 'Sesión no encontrada'
        }), 404

    # Construir path completo y validar seguridad
    file_path = os.path.join(session_path, safe_filename)

    # Verificar que el path resuelto esté dentro de session_path (prevenir path traversal)
    if not os.path.abspath(file_path).startswith(os.path.abspath(session_path)):
        return jsonify({
            'success': False,
            'error': 'Nombre de archivo inválido'
        }), 400

    # Validar existencia de archivo
    if not os.path.exists(file_path):
        return jsonify({
            'success': False,
            'error': 'Archivo no encontrado'
        }), 404

    # Enviar archivo - con safe_filename
    return send_from_directory(session_path, safe_filename, as_attachment=True)

@scan_bp.route('/cancel', methods=['POST'])
def cancel_scan():
    """
    Cancela la sesión de escaneo activa y limpia los archivos temporales.
    ---
    tags:
      - Cancelar
    summary: Cancelar escaneo en curso
    description: |
      Finaliza el escaneo actual, elimina las imágenes temporales asociadas
      a la sesión, libera el lock de la sesión y reinicia el estado interno.
      Se valida que haya un escaneo activo antes de intentar cancelar.
      
    responses:
      200:
        description: Escaneo cancelado correctamente
        examples:
          application/json: {
              "success": true,
              "message": "Escaneo cancelado correctamente"
          }
      400:
        description: No hay escaneo activo
        examples:
          application/json: {
              "success": false,
              "error": "No hay escaneo activo para cancelar"
          }
    """
    with state_lock:
        if not scan_state['is_scanning']: 
            return jsonify({
                'success': False,
                'error': 'No hay escaneo activo para cancelar'
            }), 400
        
        session_id = scan_state['session_id']
        file_manager = scan_state['file_manager']

        # Reiniciar estado solo si se liberó el lock
        reset_scan_state()

    # Liberar bloqueo
    lock_released = False
    try:
        session_manager.release_lock(session_id)
        lock_released = True
    except Exception as e:
        logger.error(f"Error al liberar lock de sesión {session_id}: {e}")

    # Limpiar archivos
    cleanup_result = {'success': True, 'files_removed': 0}
    if file_manager:
        try:
            cleanup_result = file_manager.cleanup_session()
        except Exception as e:
            logger.warning(f"Error al limpiar archivos de sesión {session_id}: {e}")
            cleanup_result = {'success': False, 'error': str(e)}
    
    return jsonify({
        'success': True,
        'message': 'Escaneo cancelado correctamente',
    })

# --- SCAN FINISH 2 PARA ELIMINAR LA SESION Y TAMBIEN LA CARPETA CON LAS IMAGENES ---
@scan_bp.route('/finish', methods=['POST'])
def finish_scan():
    """
    Finaliza la sesión de escaneo activa y libera el escáner.
    ---
    tags:
      - Finalizar
    summary: Terminar sesión de escaneo y limpiar archivos
    description: |
      Este endpoint finaliza la sesión de escaneo en curso, libera el lock
      del escáner y elimina todos los archivos escaneados asociados a la sesión.
      Útil para liberar recursos y limpiar la carpeta de escaneo después de procesar imágenes.
      Si no hay sesión activa, retorna un error 400.
    responses:
      200:
        description: Sesión finalizada y archivos eliminados correctamente.
        examples:
          application/json: {
              "success": true,
              "message": "Sesión finalizada correctamente. Archivos procesados y eliminados.",
              "session_id": "session_12345"
          }
      400:
        description: No hay sesión activa para finalizar.
        examples:
          application/json: {
              "success": false,
              "error": "No hay sesión activa para finalizar"
          }
    """
    with state_lock:
        if not scan_state['is_scanning']:
            return jsonify({
                'success': False,
                'error': 'No hay sesión activa para finalizar'
            }), 400
        
        session_id = scan_state['session_id']
        file_manager = scan_state['file_manager']
        
        # resetear estado en memoria
        reset_scan_state()
    
    # obtener paginas fuera del lock con manejo de errores
    pages = []
    if file_manager:
        try:
            pages = file_manager.get_scanned_pages()
        except Exception as e:
            logger.warning(f"Error al obtener páginas de {session_id}: {e}")
            pages = []

    # Liberar bloqueo del escáner y cerrar sesión
    lock_released = False
    try:
        session_manager.release_lock(session_id)
        lock_released = True
    except Exception as e:
        logger.error(f"Error al liberar lock de sesión {session_id}: {e}")

    # Limpiar archivos de la sesión (opcional)
    cleanup_result = {'success': True}
    if file_manager:
        try:
            cleanup_result = file_manager.cleanup_session()
            logger.info(f"Sesión {session_id} finalizada y carpeta eliminada correctamente.")
        except Exception as e:
            logger.warning(f"No se pudieron borrar archivos de la sesión {session_id}: {e}")
            cleanup_result = {'success': False, 'error': str(e)}

    return jsonify({
        'success': True,
        'message': 'Sesión finalizada correctamente. Archivos procesados y eliminados.',
        'session_id': session_id,
    })

@scan_bp.route('/cleanup/<session_id>', methods=['DELETE'])
def cleanup_session(session_id):
    """
    Elimina los archivos de una sesión específica de escaneo.
    ---
    tags:
      - Limpieza
    summary: Limpiar archivos de sesión
    description: |
      Borra los archivos temporales de la sesión indicada.
      
      Comportamiento según estado de la sesión:
      - **Sesión activa**: Elimina solo archivos PNG, mantiene carpeta para continuar escaneando
      - **Sesión inactiva**: Elimina carpeta completa con todos los archivos
      
      Útil para que Django libere espacio después de procesar las imágenes.
      
    parameters:
      - in: path
        name: session_id
        required: true
        type: string
        description: ID de la sesión a limpiar (acepta formatos "123" o "session_123")
    responses:
      200:
        description: Limpieza realizada correctamente
        examples:
          application/json:
            sesion_activa:
              value:
                success: true
                message: "Archivos de la sesión eliminados correctamente. La sesión permanece activa."
            sesion_inactiva:
              value:
                success: true
                message: "Sesión eliminada correctamente"
      404:
        description: Carpeta de sesión no encontrada
        examples:
          application/json:
            success: false
            error: "La sesión 'session_123' no existe o la carpeta ya fue eliminada."
      500:
        description: Error al limpiar la sesión
        examples:
          application/json:
            success: false
            error: "Error al limpiar la sesión"
    """
    # Normalizar session_id (acepta tanto "123" como "session_123")
    normalized = session_id if str(session_id).startswith("session_") else f"session_{session_id}"
    raw_session = session_id.replace("session_", "") if session_id.startswith("session_") else session_id

    session_path = os.path.join(SCAN_FOLDER, normalized)

    # Validar existencia de la carpeta de sesión antes de borrar
    if not os.path.isdir(session_path):
        return jsonify({
            'success': False,
            'error': f"La sesión '{normalized}' no existe o la carpeta ya fue eliminada."
        }), 404
    
    is_active_session = False
    with state_lock:
        if scan_state['session_id'] == raw_session and scan_state['is_scanning']:
            is_active_session = True

    file_manager = ScanFileManager(normalized)

    try:
        if is_active_session:
            # solo borrar archivos, mantener carpeta para futuros escaneos
            files = file_manager.get_scanned_pages()
            files_removed = 0
            
            for file_info in files:
                try:
                    file_path = os.path.join(session_path, file_info['filename'])
                    if os.path.exists(file_path):
                        os.remove(file_path)
                        files_removed += 1
                except Exception as e:
                    logger.warning(f"Error al eliminar archivo {file_info['filename']}: {e}")
                    
            # actualizar progreso en memoria
            with state_lock:
                if scan_state['session_id'] == raw_session:
                    scan_state['progress'].update({
                        'pages_scanned': 0,
                        'status': 'ready',
                        'message': 'Archivos de sesión eliminados. Listo para nuevo escaneo.'
                    })
            
            return jsonify({
                'success': True,
                'message': f"Archivos de la sesión eliminados correctamente. La sesión permanece activa.",
            })
        else:
            # Sesión incativa: borrar carpeta completa (comportamiento original)
            result = file_manager.cleanup_session()
            return jsonify(result)
    except Exception as e:
        logger.error(f"Error al limpiar sesión {normalized}: {e}")
        return jsonify({
            'success': False,
            'error': 'Error al limpiar la sesión'
        }), 500


@scan_bp.route('/delete-page/<session_id>/<filename>', methods=['DELETE'])
def delete_page(session_id, filename):
    # Sanitizar filename
    """
        Elimina una página específica de una sesión de escaneo.
    """
    safe_filename = secure_filename(filename)
    if not safe_filename:
        return jsonify({
            'success': False,
            'error': 'Nombre de archivo inválido'
        }), 400

    # Solo permitir WEBP o PNG legacy
    if not safe_filename.lower().endswith(('.webp', '.png')):
        return jsonify({
            'success': False,
            'error': 'Solo se permiten eliminar archivos con terminación .WEBP o .PNG'
        }), 400

    # Normalizar session_id: agregar prefijo si no lo tiene
    normalized_session = session_id if session_id.startswith("session_") else f"session_{session_id}"
    raw_session = session_id.replace("session_", "") if session_id.startswith("session_") else session_id
    lock_file_path = LOCK_FILE

    session_path = os.path.join(SCAN_FOLDER, normalized_session)

    # Validar que la sesión exista
    if not os.path.isdir(session_path):
        return jsonify({
            'success': False,
            'error': f'Sesión {normalized_session} no encontrada'
        }), 404

    # Construir path y validar seguridad
    file_path = os.path.join(session_path, safe_filename)
    if not os.path.abspath(file_path).startswith(os.path.abspath(session_path)):
        return jsonify({
            'success': False,
            'error': 'Nombre de archivo inválido'
        }), 400

    # Obtener lista de páginas actuales
    file_manager = ScanFileManager(normalized_session)
    try:
        pages_before = file_manager.get_scanned_pages()
    except Exception as e:
        logger.error(f"Error al obtener páginas de {normalized_session}: {e}")
        return jsonify({
            'success': False,
            'error': 'Error al leer archivos de la sesión'
        }), 500

    # Validar que el archivo exista
    if not os.path.exists(file_path):
        logger.info(f"Archivo {safe_filename} no encontrado en Flask para sesión {normalized_session}")
        return jsonify({
            'success': True,
            'message': f'Archivo no existe en Flask',
            'pages_remaining': len(pages_before),
            'session_closed': False,
            'file_not_in_flask': True
        }), 200

    finalizar_sesion = request.args.get('finalizar_sesion', 'false').lower() == 'true'

    if len(pages_before) <= 1:
        try:
            os.remove(file_path)
            logger.info(f"Última página {safe_filename} eliminada (posible cierre de sesión)")
        except Exception as e:
            logger.error(f"Error al eliminar archivo: {e}")
            return jsonify({'success': False, 'error': f'Error al eliminar archivo: {str(e)}'}), 500

        # Recontar páginas después de eliminar
        pages_after = file_manager.get_scanned_pages()
        if finalizar_sesion and len(pages_after) == 0:
            # Solo cerrar sesión si ya no quedan imágenes en la carpeta
            lock_released = False
            lock_file_deleted = False
            state_reset = False
            try:
                # 1. Resetear estado si es la sesión activa
                with state_lock:
                    if scan_state['session_id'] == raw_session:
                        reset_scan_state()
                        state_reset = True
                        logger.info(f"Estado en memoria reseteado para sesión {raw_session}")

                # 2. Liberar lock
                try:
                    session_manager.release_lock(raw_session)
                    lock_released = True
                    logger.info(f"Lock de sesión {raw_session} liberado")
                except Exception as e:
                    logger.warning(f"No se pudo liberar lock de {raw_session}: {e}")

                # 3. Eliminar archivo lock
                try:
                    if os.path.exists(lock_file_path):
                        os.remove(lock_file_path)
                        lock_file_deleted = True
                        logger.info(f"Archivo {lock_file_path} eliminado")
                except Exception as e:
                    logger.warning(f"No se pudo eliminar lock file: {e}")

                # 4. Eliminar carpeta completa
                file_manager.cleanup_session()
                logger.info(f"Carpeta de sesión {normalized_session} eliminada completamente")

                return jsonify({
                    'success': True,
                    'message': 'Última página eliminada. Sesión finalizada automáticamente.',
                    'session_closed': True
                }), 200

            except Exception as e:
                logger.error(f"Error al finalizar sesión en delete_page: {e}")
                # Intentar liberar recursos aunque haya fallado
                if not lock_released:
                    try:
                        session_manager.release_lock(raw_session)
                        logger.info(f"Lock liberado en bloque de error para {raw_session}")
                    except Exception as e2:
                        logger.error(f"No se pudo liberar lock en bloque de error: {e2}")

                if not lock_file_deleted:
                    try:
                        if os.path.exists(lock_file_path):
                            os.remove(lock_file_path)
                            logger.info("Lock file eliminado en bloque de error")
                    except Exception as e3:
                        logger.error(f"No se pudo eliminar lock file en bloque de error: {e3}")

                return jsonify({
                    'success': False,
                    'error': f'Error al finalizar sesión: {str(e)}',
                    'state_reset': state_reset,
                    'lock_released': lock_released,
                    'lock_file_deleted': lock_file_deleted
                }), 500
        else:
            # No cerrar sesión, solo reportar eliminación
            return jsonify({
                'success': True,
                'message': 'Última página de Flask eliminada. Sesión permanece activa.',
                'pages_remaining': len(pages_after),
                'session_closed': False
            }), 200


    # CASO NORMAL: AÚN QUEDAN PÁGINAS EN FLASK
    try:
        os.remove(file_path)
        logger.info(f"Página {safe_filename} eliminada ({len(pages_before) - 1} páginas restantes)")

        # Actualizar progreso si es sesión activa
        with state_lock:
            if scan_state['session_id'] == raw_session and scan_state['file_manager']:
                try:
                    pages_after = scan_state['file_manager'].get_scanned_pages()
                    scan_state['progress']['pages_scanned'] = len(pages_after)
                    scan_state['progress']['message'] = (
                        f'Página {safe_filename} eliminada. {len(pages_after)} páginas restantes.'
                    )
                except Exception as e:
                    logger.warning(f"Error al actualizar progreso: {e}")

        pages_remaining = len(file_manager.get_scanned_pages())

        return jsonify({
            'success': True,
            'message': f'Página {safe_filename} eliminada correctamente',
            'pages_remaining': pages_remaining,
            'session_closed': False
        }), 200

    except Exception as e:
        logger.error(f"Error al eliminar archivo: {e}")
        return jsonify({
            'success': False,
            'error': f'Error al eliminar archivo: {str(e)}'
        }), 500



# se usa para la eliminación multiple, para que cada imagen no tenga que consultar un endpoint de eliminación individual, lo que mejora el rendimiento y reduce la sobrecarga en el servidor al eliminar varias páginas a la vez.   
@scan_bp.route('/delete-pages', methods=['POST'])
def delete_pages():
    """
    Eliminación múltiple de páginas (robusto).
    """
    try:
        data = request.get_json() or {}
        session_id = data.get('session_id')
        filenames = data.get('filenames', [])

        if not session_id or not filenames:
            return jsonify({
                'success': False,
                'error': 'session_id y filenames son requeridos'
            }), 400

        # Normalizar session_id
        normalized_session = session_id if session_id.startswith("session_") else f"session_{session_id}"
        session_path = os.path.join(SCAN_FOLDER, normalized_session)

        if not os.path.isdir(session_path):
            return jsonify({
                'success': False,
                'error': f'Sesión {normalized_session} no encontrada'
            }), 404

        eliminadas = 0
        errores = []

        for filename in filenames:
            try:
                safe_filename = secure_filename(filename)

                if not safe_filename.lower().endswith(('.webp', '.png')):
                    errores.append(f"{filename}: extensión inválida")
                    continue

                file_path = os.path.join(session_path, safe_filename)

                if os.path.exists(file_path):
                    os.remove(file_path)
                    eliminadas += 1
                else:
                    logger.info(f"[BATCH DELETE] No existe: {safe_filename}")

            except Exception as e:
                logger.error(f"[BATCH DELETE] Error eliminando {filename}: {e}")
                errores.append(f"{filename}: {str(e)}")

        # CALCULAR RESTANTES
        try:
            pages_remaining = len([
                f for f in os.listdir(session_path)
                if f.lower().endswith(('.webp', '.png'))
            ])
        except Exception:
            pages_remaining = 0

        # RESPUESTA SIEMPRE
        return jsonify({
            'success': True,
            'message': f'{eliminadas} imágenes eliminadas',
            'deleted': eliminadas,
            'errors': errores,
            'pages_remaining': pages_remaining,
            'session_closed': pages_remaining == 0
        }), 200

    except Exception as e:
        logger.exception("[BATCH DELETE] Error crítico")

        return jsonify({
            'success': False,
            'error': f'Error interno: {str(e)}'
        }), 500

@scan_bp.route('/check-feeder', methods=['GET'])
def check_feeder_status():
    """
    Verifica el estado de la bandeja automática (ADF) del escáner.
    ---
    tags:
      - Escáner
    summary: Comprobar ADF del escáner
    description: |
      Este endpoint revisa si la bandeja automática (Feeder/ADF) del escáner
      está disponible y responde dentro del timeout configurado.
      Retorna 200 si está listo tanto si tiene papel o no, o 504 si hay límite de tiempo.
    responses:
      200:
        description: ADF disponible (con o sin papel).
        examples:
          application/json:
            con_papel:
              value:
                success: true
                message: "ADF listo para escanear"
            sin_papel:
              value:
                success: false
                message: "No hay papel en el alimentador"
      504:
        description: Timeout al verificar ADF.
        examples:
          application/json:
            success: false
            timeout: true
            message: "Timeout al comprobar ADF. Verifique que esté encendido y conectado."
    """
    status = check_feeder()
    if is_scanner_timeout(status):
        return jsonify(status), 504
    return jsonify(status)

@scan_bp.route('/check-flatbed', methods=['GET'])
def check_flatbed_status():
    """
    Verifica el estado del cristal (flatbed) del escáner.
    ---
    tags:
      - Escáner
    summary: Comprobar cristal del escáner
    description: |
      Revisa si el cristal (flatbed) del escáner está disponible y responde
      dentro del timeout configurado.
      
      Posibles respuestas:
      - **200 con success=true**: Cristal listo con hoja
      - **200 con success=false**: Cristal vacío o sin hoja
      - **504**: Timeout (escáner no responde)
      
    responses:
      200:
        description: Cristal disponible (con o sin hoja).
        examples:
          application/json:
            con_hoja:
              value:
                success: true
                message: "Cristal listo para escanear"
            sin_hoja:
              value:
                success: false
                message: "No hay hoja en el cristal"
      504:
        description: Tiempo límite al verificar cristal.
    """
    status = check_flatbed_sheet()
    if is_scanner_timeout(status):
        return jsonify(status), 504
    return jsonify(status)

@scan_bp.route('/health', methods=['GET'])
def health_check():
    """
    Health check mejorado para monitoreo externo.
    ---
    tags:
      - Sistema
    summary: Verificar estado del servicio
    description: |
      Endpoint para que sistemas externos (Django, watchdog, NSSM, load balancer)
      puedan verificar que el servicio está funcionando correctamente.
      
      Incluye información sobre:
      - Estado del servicio
      - Configuración del escáner
      - Disponibilidad del escáner
      - Sesión de escaneo activa (y espacio en disco)
      - Existencia de Tesseract
      
      Útil para:
      - Monitoreo de servicios de Windows (NSSM)
      - Health checks en balanceadores de carga
      - Validación desde Django antes de permitir escaneos
      - Alertas automáticas si el servicio falla
      
    responses:
      200:
        description: Servicio saludable y operativo
        examples:
          application/json:
            servicio_listo:
              value:
                status: "healthy"
                timestamp: "2024-01-15T10:30:00"
                scanner:
                  configured: "e-STUDIO2822ASeries Scan Driver"
                  available: true
                session:
                  active: false
                  session_id: null
                version: "1.0.0"
                checks: 
                   disk: "up"
                   tesseract: "up"
            servicio_escaneando:
              value:
                status: "healthy"
                timestamp: "2024-01-15T10:35:00"
                scanner:
                  configured: "e-STUDIO2822ASeries Scan Driver"
                  available: true
                session:
                  active: true
                  session_id: "abc123"
                version: "1.0.0"
      503:
        description: Servicio no saludable (falla crítica)
      500:
        description: Servicio no saludable (error interno)
    """
    checks = {
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'version': '1.0.0',
        'checks': {}
    }
    
    # 1. Verificar escáner (lógica original + validación de nombre)
    try:
        # Obtener estado de escaneo actual
        with state_lock:
            scanning = scan_state['is_scanning']
            session_id = scan_state['session_id']
        
        # Validar disponibilidad del escáner configured vs available
        scanner_available = None
        if not scanning:
             try:
                import twain
                import ctypes
                ctypes.windll.kernel32.SetDllDirectoryW(None)
                SM = twain.SourceManager(0)
                if SM:
                    available_scanners = SM.GetSourceList()
                    scanner_available = settings.scanner_name in available_scanners
             except Exception:
                pass
        
        checks['scanner'] = {
            'configured': settings.scanner_name,
            'available': scanner_available,
            'status': 'up' if scanner_available is not False else 'warning'
        }
        checks['session'] = {
            'active': scanning,
            'session_id': session_id
        }

    except Exception as e:
        checks['checks']['scanner'] = {'status': 'down', 'error': str(e)}

    # 2. Verificar espacio en disco
    try:
        if not os.path.exists(SCAN_FOLDER):
            os.makedirs(SCAN_FOLDER, exist_ok=True)
            
        stat = shutil.disk_usage(SCAN_FOLDER)
        free_gb = stat.free / (1024**3)
        checks['checks']['disk'] = {
            'status': 'up' if free_gb > 1 else 'warning',
            'free_gb': round(free_gb, 2)
        }
    except Exception as e:
        checks['checks']['disk'] = {'status': 'down', 'error': str(e)}
    
    # 3. Verificar Tesseract
    try:
        tesseract_exists = os.path.exists(settings.tesseract_cmd)
        checks['checks']['tesseract'] = {
            'status': 'up' if tesseract_exists else 'warning',
            'path': settings.tesseract_cmd
        }
    except Exception as e:
        checks['checks']['tesseract'] = {'status': 'down', 'error': str(e)}
    
    # Determinar status general
    if any(c.get('status') == 'down' for c in checks['checks'].values()):
        checks['status'] = 'unhealthy'
        return jsonify(checks), 503
    elif any(c.get('status') == 'warning' for c in checks['checks'].values()):
        checks['status'] = 'degraded'
        return jsonify(checks), 200
    
    return jsonify(checks), 200

@scan_bp.route('/reset-driver', methods=['POST'])
def reset_driver_state():
    """
    Reinicia el estado interno del driver TWAIN cuando se detecta corrupción.
    ---
    tags:
      - Mantenimiento
    summary: Reiniciar estado del driver
    description: |
      Limpia threads zombies, libera locks y resetea contadores internos.
      Útil cuando el driver TWAIN entra en estado corrupto después de múltiples timeouts.
      
      **IMPORTANTE:** Esto NO reinicia el escáner físicamente. Si persisten errores,
      apague y encienda el escáner manualmente.
      
      El campo `was_scanning` indica si había una sesión activa que fue cancelada.
    
    responses:
      200:
        description: Estado reiniciado correctamente
        examples:
          application/json:
            sin_sesion_activa:
              value:
                success: true
                message: "Estado del driver reiniciado. Si persisten errores, reinicie el escáner físicamente."
                zombies_cleared: 0
                lock_released: true
                was_scanning: false
            con_sesion_activa:
              value:
                success: true
                message: "Estado del driver reiniciado. Si persisten errores, reinicie el escáner físicamente."
                zombies_cleared: 3
                lock_released: true
                was_scanning: true
    """
    global _zombie_threads
    
    logger.warning("[RESET-DRIVER] Reiniciando estado del driver TWAIN...")
    
    zombies_before = _zombie_threads
    
    # Liberar hardware lock si está trabado
    lock_released = False
    try:
        _hardware_lock.release()
        lock_released = True
    except RuntimeError:
        logger.debug(f"[CONTEXTO] Error ignorado al liberar hardware lock (no estaba adquirido)")
    
    # Resetear contador de zombies
    _zombie_threads = 0
    
    # Resetear estado de escaneo
    with state_lock:
        was_scanning = scan_state['is_scanning']
        reset_scan_state()
    
    return jsonify({
        'success': True,
        'message': 'Estado del driver reiniciado. Si persisten errores, reinicie el escáner físicamente.',
        'lock_released': lock_released,
        'was_scanning': was_scanning
    }), 200
    
# Restaurar sesión al cargar el módulo
restore_session_from_lock()