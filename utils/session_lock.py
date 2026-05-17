# utils/session_lock.py

"""
    Módulo para manejar el bloqueo de sesiones del escáner.
    Permite evitar que múltiples usuarios accedan al escáner simultáneamente.
    Utiliza un archivo de bloqueo para registrar la sesión activa, con información como
    el ID de sesión, usuario, tiempo de inicio y estado.
"""
# 1. standard library imports
import logging  # Para logging de eventos
import os # para manejo de rutas y sistema de archivos
import json # para manejo de archivos JSON
from typing import Optional
import uuid # para generar IDs únicos
from datetime import datetime, timedelta # para manejo de tiempos

# 3. First party (local) imports
from config.settings import settings # Importar la ruta base del proyecto desde el modulo de config

logger = logging.getLogger(__name__) # Logger específico para este módulo

# Archivo donde se guarda la información de la sesión activa
# Este es el archivo que se crea cuando hay una sesion activa y permite bloquear el escaner.
# Se crea en la raiz del proyecto
try:
    BASE_DIR = getattr(settings, 'base_dir', None)
except Exception:
    BASE_DIR = None

# Asegurarse de tener la ruta base donde se creará el lock file
if not BASE_DIR:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Ruta completa y nombre del archivo de lock
LOCK_FILE = os.path.join(BASE_DIR, "scanner_session.lock")

class SessionLock:
    """
    Maneja el bloqueo de sesiones del escáner para evitar uso concurrente.
    Solo permite una sesión activa a la vez por escáner.
    Attributes:
        lock_file (str): Ruta al archivo de bloqueo de sesión
        active_session (dict): Información sobre la sesión activa, si existe
    """

    def __init__(self):
        self.lock_file = LOCK_FILE
        # self.active_session = None
        os.makedirs(os.path.dirname(self.lock_file), exist_ok=True)

    # El timeout por defecto se toma desde settings.cleanup_session_timeout_minutes.
    # Se puede sobrescribir al adquirir la sesión.
    def acquire_lock(self, user_id: str ="unknown", timeout_minutes: Optional[int] = None, scanner_name: Optional[str] = None):
        """
        Intenta adquirir el bloqueo del escáner.

        Args:
            user_id (str): Identificador del usuario que solicita el bloqueo
            timeout_minutes (int): Tiempo máximo de la sesión en minutos

        Returns:
            dict: {'success': bool, 'session_id': str, 'message': str}
        """
        if timeout_minutes is None:
            timeout_minutes = settings.cleanup_session_timeout_minutes

        if timeout_minutes <= 0:
            return {
                'success': False,
                'session_id': None,
                'message': 'El tiempo de sesión debe ser mayor a 0 minutos'
            }

        # Verificar si ya existe una sesión activa
        if self.is_locked():
            active_session = self._get_active_session() # obtener datos de la sesion activa
            if active_session:
                return {
                    'success': False,
                    'session_id': None,
                    'message': f"Escáner ocupado por {active_session.get('user_id', 'usuario desconocido')}",
                    'active_session': active_session
                }

        # Crear nueva sesión
        session_id = str(uuid.uuid4()) # nuevo ID único para la sesión
        normalized_scanner = None
        if isinstance(scanner_name, str):
            normalized_scanner = scanner_name.strip() or None

        session_data = {
            'session_id': session_id,
            'user_id': user_id,
            'start_time': datetime.now().isoformat(), # tiempo de inicio en formato ISO
            'timeout_minutes': timeout_minutes, 
            'status': 'active',
            'scanner_name': normalized_scanner
        }

        try:
            # Escritura atómica del archivo de bloqueo, es decir, solo se crea si no existe
            fd = os.open(self.lock_file, os.O_CREAT | os.O_EXCL| os.O_WRONLY)
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(session_data, f, indent=2, ensure_ascii=False)
            logger.info("Sesión iniciada session_id=%s user_id=%s", session_id, user_id)
            return {
                'success': True,
                'session_id': session_id,
                'message': 'Sesión iniciada correctamente',
                'session': session_data
            }
        except FileExistsError:
            active_session = self._get_active_session()
            return {
                'success': False,
                'session_id': None,
                'message': f"Escáner ocupado por {active_session.get('user_id', 'usuario desconocido')}",
                'active_session': active_session
            }
        except Exception as e:
            logger.error("Error al crear sesión: %s", e, exc_info=True)
            return {
                'success': False,
                'session_id': None,
                'message': f"Error al crear sesión: {str(e)}"
            }

    def release_lock(self, session_id: Optional[str] = None):
        """
        Libera el bloqueo del escáner.

        Args:
            session_id (str): ID de la sesión a liberar (opcional para verificación)

        Returns:
            dict: {'success': bool, 'message': str}
        """
        if not os.path.exists(self.lock_file):
            logger.info("No había sesión activa al intentar liberar lock.")
            return {
                'success': True,
                'message': 'No hay sesión activa para liberar'
            }

        # si se proporciona session_id, verificar que coincida
        if session_id:
            active_session = self._get_active_session()
            if active_session and active_session.get('session_id') != session_id:
                return {
                    'success': False,
                    'message': 'ID de sesión no coincide con la sesión activa'
                }

        try:
            # if os.path.exists(self.lock_file):
            os.remove(self.lock_file)
            logger.info("Sesión liberada correctamente.")
            return {
                'success': True,
                'message': 'Sesión liberada correctamente'
            }
        except Exception as e:
            logger.error("Error al liberar sesión: %s", e, exc_info=True)
            return {
                'success': False,
                'message': f"Error al liberar sesión: {str(e)}"
            }

    def is_locked(self):
        """
        Verifica si el escáner está bloqueado por una sesión activa.
        Limpia automáticamente sesiones expiradas.

        Returns:
            bool: True si está bloqueado, False si está disponible
        """
        if not os.path.exists(self.lock_file):
            return False

        active_session = self._get_active_session()
        if not active_session:
            self._remove_lock_file_no_check()
            return False

        # Verificar si la sesión ha expirado
        if self._is_session_expired(active_session):
            logger.info("Sesión expirada, removiendo lock: session_id=%s user_id=%s",
            active_session.get("session_id"),
            active_session.get("user_id")
            )
            self._remove_lock_file_no_check()
            return False
        return True

    def get_status(self) -> dict:
        """
        Obtiene el estado actual del escáner y la sesión activa.
        
        Returns:
            dict: Estado completo del escáner
        """
        if not os.path.exists(self.lock_file):
            return {
                'scanner_busy': False,
                'message': 'Escáner disponible',
                'active_session': None
            }
        active_session = self._get_active_session()
        if not active_session:
            self._remove_lock_file_no_check()
            return {
                'scanner_busy': False,
                'message': 'Escáner disponible',
                'active_session': None
            }
        # calcular expiracion
        try:
            start_time = datetime.fromisoformat(active_session['start_time'])
            timeout_minutes = int(active_session.get('timeout_minutes', settings.cleanup_session_timeout_minutes))
            expires_at = start_time + timedelta(minutes=timeout_minutes)
            minutes_left = max(0, int((expires_at - datetime.now()).total_seconds() // 60))
        except Exception:
            expires_at = None
            minutes_left = None
        expired = self._is_session_expired(active_session)
        return {
            'scanner_busy': not expired,
            'message': f"Escaner ocupado por {active_session.get('user_id', 'usuario desconocido')}" if not expired else 'Escáner disponible',
            'active_session': None if expired else {
                **active_session,
                'expires_at': expires_at.isoformat() if expires_at else None,
                'minutes_left': minutes_left
            }
        }

    def _get_active_session(self):
        """
        Lee la información de la sesión activa desde el archivo de bloqueo.
        
        Returns:
            dict: Datos de la sesión activa o None si no existe
        """
        try:
            if not os.path.exists(self.lock_file):
                return None
            with open(self.lock_file, 'r', encoding='utf-8') as f:
                session_data = json.load(f)

            # Verificación mínima
            required_keys = ['session_id', 'user_id', 'start_time', 'status']
            if not all(k in session_data for k in required_keys):
                logger.warning("lock file corrupto: %s", {self.lock_file})
                return None
            return session_data

        except Exception as e:
            logger.warning("Error al leer archivo lock (posiblemente corrupto): %s", e)
            return None

    def _is_session_expired(self, session_data: dict) -> bool:
        """
        Verifica si una sesión ha expirado basado en el timeout.
        
        Args:
            session_data (dict): Datos de la sesión
            
        Returns:
            bool: True si la sesión ha expirado
        """
        try:
            start_time = datetime.fromisoformat(session_data['start_time'])
            # este tiempo es el que se le da al escaner para que termine su trabajo
            timeout_minutes = session_data.get('timeout_minutes', settings.cleanup_session_timeout_minutes)

            return datetime.now() > start_time + timedelta(minutes=timeout_minutes)
        except Exception:
            return True  # Si hay error, considerar expirada

    def _remove_lock_file_no_check(self):
        """
        Elimina el archivo de bloqueo sin verificar la sesión.
        Usado internamente para limpieza.
        """
        try:
            if os.path.exists(self.lock_file):
                os.remove(self.lock_file)
        except Exception as e:
            logger.error("Error al eliminar archivo de lock de sesión: %s", e)

    def update_session_scanner(self, scanner_name: Optional[str], session_id: Optional[str] = None) -> dict:
        """
        Actualiza scanner_name de la sesión activa sin recrear el lock.

        Args:
            scanner_name (str|None): Nombre de escáner a persistir
            session_id (str|None): Si se envía, valida que coincida con la sesión activa

        Returns:
            dict: {'success': bool, 'message': str}
        """
        if not os.path.exists(self.lock_file):
            return {
                'success': False,
                'message': 'No hay sesión activa para actualizar scanner_name'
            }

        try:
            with open(self.lock_file, 'r', encoding='utf-8') as f:
                session_data = json.load(f)

            if session_id and session_data.get('session_id') != session_id:
                return {
                    'success': False,
                    'message': 'ID de sesión no coincide con la sesión activa'
                }

            normalized_scanner = None
            if isinstance(scanner_name, str):
                normalized_scanner = scanner_name.strip() or None

            session_data['scanner_name'] = normalized_scanner

            with open(self.lock_file, 'w', encoding='utf-8') as f:
                json.dump(session_data, f, indent=2, ensure_ascii=False)

            return {
                'success': True,
                'message': 'scanner_name de sesión actualizado'
            }
        except Exception as e:
            logger.error("Error al actualizar scanner_name de sesión: %s", e, exc_info=True)
            return {
                'success': False,
                'message': f"Error al actualizar scanner_name: {str(e)}"
            }

# Instancia global para usar en toda la aplicación
session_manager = SessionLock()
