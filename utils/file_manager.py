# utils/file_manager.py

"""
Módulo para manejar archivos temporales de escaneo.
Guarda páginas escaneadas como WEBP (o PNG legacy) en carpetas de sesión.
"""

# 1. Standard library imports
import os
import shutil
import logging
from datetime import datetime
from typing import Optional
from PIL import Image

# 3. First party (local) imports
from config.config import SCAN_FOLDER
from config.settings import settings

# Configurar el logger para este módulo
logger = logging.getLogger(__name__)

class ScanFileManager:
    """
    Maneja los archivos de imagen temporales del proceso de escaneo.
    Guarda cada página con nomenclatura secuencial.
    """

    def __init__(self, session_id: str):
        # Normalizar: si ya trae 'session_' no lo volvemos a anteponer
        normalized=session_id if str(session_id).startswith("session_") else f"session_{session_id}"
        self.session_id = normalized
        self.session_folder = os.path.join(SCAN_FOLDER, normalized)
        self.image_format = (settings.scan_image_format or "webp").strip().lower()
        if self.image_format not in ("webp", "png"):
            self.image_format = "webp"
        self.image_extension = ".webp" if self.image_format == "webp" else ".png"
        self.allowed_extensions = (".webp", ".png")
        self.webp_quality = settings.scan_image_quality
        self.webp_method = settings.scan_image_method
        self.webp_lossless = settings.scan_image_lossless
        self._ensure_session_folder()
        self.page_counter = self._init_page_counter()

    def _ensure_session_folder(self):
        """
        Crea la carpeta de sesión si no existe.
        """
        os.makedirs(self.session_folder, exist_ok=True)

    def _resolve_target_mode(self, color_mode: Optional[str], img: Image.Image) -> str:
        """
        Define el modo de color de salida según el modo de escaneo.
        """
        normalized = (color_mode or "").strip().lower()
        if normalized in ("color", "text/photo"):
            return "RGB"
        if normalized in ("text", "gray", "grayscale"):
            return "L"
        if img.mode == "RGBA":
            return "RGB"
        if img.mode == "1":
            return "L"
        if img.mode in ("L", "RGB"):
            return img.mode
        return "RGB"

    def _prepare_image(self, image, color_mode: Optional[str]):
        """
        Abre y convierte la imagen según el modo de escaneo.
        """
        if isinstance(image, str):
            with Image.open(image) as im:
                target_mode = self._resolve_target_mode(color_mode, im)
                return im.convert(target_mode)

        target_mode = self._resolve_target_mode(color_mode, image)
        if image.mode != target_mode:
            return image.convert(target_mode)
        return image

    def _init_page_counter(self) -> int:
        """
        Determina el siguiente número de página según los archivos existentes.
        Evita sobrescribir si se reanuda una sesión.
        """
        try:
            if not os.path.exists(self.session_folder):
                return 1
            existing = [
                fname for fname in os.listdir(self.session_folder)
                if fname.lower().endswith(self.allowed_extensions)
            ]
            if not existing:
                return 1
            # Intentar extraer índice de nombres tipo page_XX
            max_idx = 0
            for fname in existing:
                name = os.path.splitext(fname)[0] # Solo tomar el nombre sin extensión
                if name.startswith("page_"):
                    try:
                        idx = int(name.split("_", 1)[1])
                        max_idx = max(max_idx, idx)
                    except (ValueError, IndexError):
                        continue
            return max_idx + 1
        except (OSError, PermissionError) as e:
            logger.debug("No se pudo inicializar page_counter: %s", e, exc_info=True)
            return 1

    def set_page_counter(self, value: int):
        """
        Permite establecer manualmente el contador de páginas.
        Útil para sincronizar con Django cuando se eliminan o reordenan páginas.
        
        Args:
            value (int): Nuevo valor del contador de páginas.
        """
        self.page_counter = int(value)
        logger.debug(f"Contador de páginas establecido a {self.page_counter}")

    def get_next_page_filename(self) -> str:
        """
        Devuelve el nombre del siguiente archivo de página sin incrementar el contador.
        Útil para saber cómo se llamará la próxima imagen antes de guardarla.
        
        Returns:
            str: Nombre del archivo (ej: 'page_05.webp')
        """
        return f"page_{self.page_counter:02d}{self.image_extension}"

    def _next_filename(self, custom_filename: Optional[str]) -> str:
        """
        Genera el siguiente nombre de archivo secuencial.
        Si se proporciona custom_filename, lo usa en su lugar.
        """
        if custom_filename:
            return f"{custom_filename}{self.image_extension}"
        while True:
            candidate = f"page_{self.page_counter:02d}{self.image_extension}"
            if not os.path.exists(os.path.join(self.session_folder, candidate)):
                return candidate
            self.page_counter += 1


    def save_page(self, image, custom_filename=None, color_mode: Optional[str] = None):
        """
        Guarda una imagen con el formato configurado y nombre secuencial.

        Args:
            image: Objeto PIL.Image o ruta a archivo BMP
            custom_filename (str, optional): Nombre personalizado sin extensión
            color_mode (str, optional): Modo de color de escaneo (Text, Gray, Color, Text/Photo)

        Returns:
            dict: {'success': bool, 'filename': str, 'full_path': str, 'file_path': str, 
                'page_number': int, 'file_size': int}
                O {'success': False, 'error': str} si falla
        """
        img = None
        image_is_path = isinstance(image, str)
        try:
            # Abrir/convertir imagen
            img = self._prepare_image(image, color_mode)

            # Determinar filename y page_number
            if custom_filename:
                filename = f"{custom_filename}{self.image_extension}"
                page_number = None
            else:
                filename = self.get_next_page_filename()
                page_number = self.page_counter

            # Construir ruta completa (UNA SOLA VEZ)
            full_path = os.path.join(self.session_folder, filename)

            # Guardar imagen (UNA SOLA VEZ)
            if self.image_format == "webp":
                img.save(
                    full_path,
                    format="WEBP",
                    quality=self.webp_quality,
                    method=self.webp_method,
                    lossless=self.webp_lossless
                )
            else:
                img.save(full_path, format="PNG", optimize=True, compress_level=6)

            # Incrementar contador SOLO si fue exitoso y no es custom
            if not custom_filename:
                self.page_counter += 1

            # Retornar resultado
            return {
                'success': True,
                'filename': filename,
                'full_path': full_path,
                'file_path': full_path,
                'page_number': page_number,
                'file_size': os.path.getsize(full_path)
            }

        except (OSError, PermissionError, Image.UnidentifiedImageError) as e:
            logger.error("Error guardando webp: %s", e, exc_info=True)
            return {
                'success': False,
                'error': str(e),
                'filename': None,
                'full_path': None,
                'file_path': None,
                'page_number': None
            }
        finally:
            # Cerrar imagen si fue creada desde archivo
            if img is not None and (image_is_path or img is not image):
                try:
                    img.close()
                except:
                    pass

    save_page_as_webp = save_page
    save_page_as_png = save_page

    def save_bmp_as_png(self, bmp_path: str):
        """
        Convierte un archivo BMP al formato configurado y elimina el BMP original.

        Args:
            bmp_path (str): Ruta al archivo BMP.

        Returns:
            dict: Resultado de la conversión.
        """
        try:
            result = self.save_page(bmp_path)

            if result.get('success') and os.path.exists(bmp_path):
                try:
                    os.remove(bmp_path)
                    result['bmp_removed'] = True
                except OSError as e:
                    logger.debug("No se pudo eliminar BMP original: %s", e)
                    result['bmp_removed'] = False

            return result

        except (OSError, IOError) as e:
            logger.error("Error al convertir BMP: %s", e, exc_info=True)
            return {
                'success': False,
                'error': f"Error al convertir BMP: {str(e)}",
                'bmp_removed': False
            }

    def get_scanned_pages(self):
        """
        Obtiene la lista de páginas escaneadas en la sesión.

        Returns:
            list: Diccionarios con información de cada página.
        """
        pages = []

        if not os.path.exists(self.session_folder):
            return pages

        for filename in os.listdir(self.session_folder):
            if filename.lower().endswith(self.allowed_extensions):
                file_path = os.path.join(self.session_folder, filename)
                try:
                    pages.append({
                        'filename': filename,
                        'full_path': file_path,
                        'size': os.path.getsize(file_path),
                        'modified': datetime.fromtimestamp(os.path.getmtime(file_path)).isoformat()
                    })
                except (OSError, ValueError):
                    continue

        # Ordenar por nombre (page_01, page_10, etc.)
        pages.sort(key=lambda x: x['filename'])
        return pages

    def get_page_count(self):
        """Obtiene el número de páginas escaneadas."""
        return len(self.get_scanned_pages())

    def cleanup_session(self):
        """
        Elimina toda la carpeta de sesión y sus archivos.

        Returns:
            dict: {'success', 'message', 'files_removed'}
        """
        try:
            if os.path.exists(self.session_folder):
                files_count = len([
                    f for f in os.listdir(self.session_folder)
                    if f.lower().endswith(self.allowed_extensions)
                ])

                shutil.rmtree(self.session_folder)

                return {
                    'success': True,
                    'message': 'Sesión limpiada correctamente',
                    'files_removed': files_count
                }

            return {
                'success': True,
                'message': 'No hay archivos para limpiar',
                'files_removed': 0
            }

        except (OSError, PermissionError) as e:
            logger.error("Error al limpiar sesión: %s", e, exc_info=True)
            return {
                'success': False,
                'message': f'Error al limpiar sesión: {str(e)}',
                'files_removed': 0
            }

    def delete_page(self, filename: str):
        """
        Elimina una página específica.

        Args:
            filename (str): Nombre del archivo a eliminar.

        Returns:
            dict: {'success', 'message'}
        """
        try:
            file_path = os.path.join(self.session_folder, filename)

            if os.path.exists(file_path) and filename.lower().endswith(self.allowed_extensions):
                os.remove(file_path)
                return {
                    'success': True,
                    'message': f'Página {filename} eliminada correctamente'
                }

            return {
                'success': False,
                'message': f'Archivo {filename} no encontrado'
            }

        except (OSError, PermissionError) as e:
            logger.error("Error al eliminar página: %s", e, exc_info=True)
            return {
                'success': False,
                'message': f'Error al eliminar página: {str(e)}'
            }

def cleanup_old_sessions(max_age_hours: int = 24):
    """
    Limpia sesiones antiguas automáticamente.

    Args:
        max_age_hours (int): Edad máxima de las sesiones en horas.

    Returns:
        dict: {'success', 'sessions_cleaned', 'message'}
    """
    try:
        cleaned_sessions = 0

        if not os.path.exists(SCAN_FOLDER):
            return {
                'success': True,
                'sessions_cleaned': 0,
                'message': 'No hay carpeta de escaneos'
            }

        current_time = datetime.now()

        for item in os.listdir(SCAN_FOLDER):
            item_path = os.path.join(SCAN_FOLDER, item)

            if os.path.isdir(item_path) and item.startswith('session_'):
                try:
                    folder_time = datetime.fromtimestamp(os.path.getctime(item_path))
                    age_hours = (current_time - folder_time).total_seconds() / 3600

                    if age_hours > max_age_hours:
                        shutil.rmtree(item_path)
                        cleaned_sessions += 1
                except (OSError, ValueError):
                    continue

        return {
            'success': True,
            'sessions_cleaned': cleaned_sessions,
            'message': f'Limpieza completada. {cleaned_sessions} sesiones eliminadas'
        }

    except (OSError, PermissionError) as e:
        logger.error("Error en limpieza automática: %s", e, exc_info=True)
        return {
            'success': False,
            'sessions_cleaned': 0,
            'message': f'Error en limpieza automática: {str(e)}'
        }
