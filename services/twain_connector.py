# services/twain_connector.py

"""
Módulo para interactuar con escáneres TWAIN en Windows.
Provee funciones para escanear documentos desde alimentador o cristal,
y para verificar el estado del alimentador y cristal.
"""

# 1. Standard library imports
import os
import shutil
import ctypes
import time
import logging
import gc
import threading

# 2. Third party imports
import numpy as np
from PIL import Image
import twain
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

# 3. first party (local) imports
from config.config import SCAN_FOLDER
from utils.file_manager import ScanFileManager
from config.settings import settings

logger = logging.getLogger(__name__)

def is_blank_page(img, content_threshold=0.01):
    """
    Detecta páginas en blanco usando análisis de desviación estándar y umbral adaptativo.
    Optimizado con NumPy para mayor velocidad.
    
    Args:
        img: Imagen PIL a analizar
        content_threshold: Porcentaje mínimo de píxeles de tinta para considerar contenido
                          - 0.01 (1%) para feeder (más estricto)
                          - 0.015 (1.5%) para flatbed (un poco más permisivo)
    
    Returns:
        bool: True si la página está en blanco
    """
    # Convertir a escala de grises
    if img.mode != 'L':
        img = img.convert('L')
    
    # Reducir resolución para análisis rápido (512px es suficiente)
    img_small = img.resize((512, int(512 * img.height / img.width)))
    data = np.array(img_small)

    # Análisis de desviación estándar
    # Página blanca/uniforme tiene std_dev < 10
    std_dev = np.std(data)
    if std_dev < 10:
        logger.debug(f"[BlankDetect] std_dev={std_dev:.2f} < 10 → BLANK (uniforme)")
        return True

    # Umbral adaptativo: considerar "tinta" lo que es 15% más oscuro que el promedio
    mean_val = np.mean(data)
    ink_threshold = mean_val * 0.85
    
    # Contar píxeles de tinta
    ink_pixels = np.sum(data < ink_threshold)
    ink_ratio = ink_pixels / data.size

    is_blank = ink_ratio < content_threshold
    
    logger.debug(
        f"[BlankDetect] std_dev={std_dev:.2f}, ink_ratio={ink_ratio:.4f} "
        f"(th={content_threshold}) → {'BLANK' if is_blank else 'SAVE'}"
    )

    return is_blank

class TwainScanError(Exception):
    """Error de escaneo TWAIN."""
    pass

def _safe_destroy(*objs):
    """Libera recursos TWAIN sin lanzar excepciones."""
    for obj in objs:
        try:
            obj.destroy()
        except Exception:
            pass


def _get_scanner_candidates(preferred_scanner=None, allow_fallback=True):
    """Construye lista priorizada de escáneres candidatos sin duplicados."""
    candidates = []

    preferred = preferred_scanner.strip() if isinstance(preferred_scanner, str) and preferred_scanner.strip() else None
    primary = getattr(settings, "scanner_name", "")
    primary = primary.strip() if isinstance(primary, str) and primary.strip() else None
    secondary = getattr(settings, "scanner_name_secondary", "")
    secondary = secondary.strip() if isinstance(secondary, str) and secondary.strip() else None

    # Fase 1: si llega scanner explícito, esa es la primera opción.
    if preferred:
        candidates.append(preferred)
        # Fase 2/3 (solo con fallback): completar con primario/secundario configurados.
        if allow_fallback:
            if primary and primary != preferred:
                candidates.append(primary)
            if secondary and secondary not in (preferred, primary):
                candidates.append(secondary)
    else:
        # Sin scanner explícito: usar configuración (primario -> secundario).
        if primary:
            candidates.append(primary)
        if allow_fallback and secondary and secondary != primary:
            candidates.append(secondary)

    unique = []
    for candidate in candidates:
        if candidate not in unique:
            unique.append(candidate)
    return unique


def _open_source_with_fallback(sm, scanners, preferred_scanner=None, allow_fallback=True):
    """Abre la primera fuente TWAIN disponible según prioridad de candidatos."""
    if not scanners:
        raise TwainScanError("No se encontraron escáneres TWAIN disponibles.")

    candidates = _get_scanner_candidates(
        preferred_scanner=preferred_scanner,
        allow_fallback=allow_fallback
    )

    # Compatibilidad: solo en modo fallback se permite usar primer escáner disponible.
    if not candidates:
        if allow_fallback:
            candidates = [scanners[0]]
        else:
            raise TwainScanError("Modo estricto activo y sin candidatos configurados para seleccionar escáner.")

    open_errors = []
    for candidate in candidates:
        if candidate not in scanners:
            continue
        try:
            source = sm.OpenSource(candidate)
            return source, candidate
        except twain.exceptions.TwainError as e:
            open_errors.append(f"{candidate}: {e}")

    # Último fallback defensivo solo si allow_fallback=True.
    if allow_fallback:
        fallback_first = scanners[0]
        if fallback_first not in candidates:
            try:
                source = sm.OpenSource(fallback_first)
                return source, fallback_first
            except twain.exceptions.TwainError as e:
                open_errors.append(f"{fallback_first}: {e}")

    detail = "; ".join(open_errors) if open_errors else "Sin detalle del driver"
    raise TwainScanError(f"No se pudo abrir ningún escáner TWAIN disponible. Detalle: {detail}")


def _iter_scanner_candidates(preferred_scanner=None, allow_fallback=True):
    """Devuelve candidatos ordenados y sin duplicados para intentar operaciones TWAIN."""
    candidates = _get_scanner_candidates(
        preferred_scanner=preferred_scanner,
        allow_fallback=allow_fallback
    )
    return [c for c in candidates if isinstance(c, str) and c.strip()]

def scan_document(
    dpi=300, color_mode="Color", duplex=False, feeder=True,
    page_size="LT-R", rotation="off", skip_blank_pages=True,
    session_id=None,
    **kwargs
):
    """
    Escanea documentos desde alimentador o cristal.
    - Si feeder=False (flatbed), intenta forzar modo crystal.
    - Si la primera página desde flatbed es blanca, cancela y elimina carpeta de sesión.
    """

    if session_id:
        session_id = session_id if str(session_id).startswith("session_") else f"session_{session_id}"
        session_folder = os.path.join(SCAN_FOLDER, session_id)
    else:
        session_folder = SCAN_FOLDER

    # Permitir pasar un file_manager ya existente (con contador sincronizado)
    file_manager = kwargs.get('file_manager', None)
    if file_manager is None:
        file_manager = ScanFileManager(session_id)

    # Asegurar que la carpeta de sesión existe
    hwnd = ctypes.windll.user32.GetForegroundWindow()

    try:
        sm = twain.SourceManager(hwnd)
    except twain.exceptions.TwainError as e:
        raise TwainScanError("No se pudo inicializar TWAIN. El escáner podría estar en uso.")

    scanners = sm.GetSourceList()
    selected_scanner = None
    preferred_scanner = kwargs.get('scanner_name')
    allow_fallback = kwargs.get('allow_fallback', True)

    try:
        source, selected_scanner = _open_source_with_fallback(
            sm,
            scanners,
            preferred_scanner=preferred_scanner,
            allow_fallback=allow_fallback
        )
        logger.info(f"🖨️ Escáner TWAIN seleccionado: {selected_scanner}")
    except TwainScanError:
        sm.destroy()
        raise

    # --- Configuración básica ---
    try:
        source.SetCapability(twain.ICAP_XRESOLUTION, twain.TWTY_FIX32, dpi)
        source.SetCapability(twain.ICAP_YRESOLUTION, twain.TWTY_FIX32, dpi)
    except Exception:
        logger.warning("⚠ Advertencia al configurar resolución")

    pixel_types = {
        "Text": twain.TWPT_BW,
        "Gray": twain.TWPT_GRAY,
        "Color": twain.TWPT_RGB,
        "Text/Photo": twain.TWPT_RGB
    }
    try:
        source.SetCapability(twain.ICAP_PIXELTYPE, twain.TWTY_UINT16, pixel_types.get(color_mode, twain.TWPT_RGB))
    except Exception:
        logger.warning("⚠ Advertencia al configurar modo de color")

    size_mapping = {
        "LT-R": twain.TWSS_USLETTER,
        "A4-R": twain.TWSS_A4,
        "13-LG": twain.TWSS_USLEGAL,
        "A5-R": twain.TWSS_A5,
    }
    try:
        twain_size = size_mapping.get(page_size, twain.TWSS_A4)
        source.SetCapability(twain.ICAP_SUPPORTEDSIZES, twain.TWTY_UINT16, twain_size)
    except Exception:
        logger.warning("⚠ Advertencia al configurar tamaño de página")

    # --- Modo feeder / flatbed ---
    if feeder:
        try:
            source.SetCapability(twain.CAP_FEEDERENABLED, twain.TWTY_BOOL, True)
            logger.info("📥 Modo ADF: alimentador automático activado")
        except Exception as e:
            logger.warning(f"⚠ No se pudo activar alimentador automático: {e}")
    else:
        # Intentamos forzar flatbed lo más que el driver permita
        try:
            source.SetCapability(twain.CAP_FEEDERENABLED, twain.TWTY_BOOL, False)
        except Exception:
            pass
        try:
            source.SetCapability(twain.CAP_AUTOFEED, twain.TWTY_BOOL, False)
        except Exception:
            pass
        try:
            # desactivar duplex para evitar conflicto
            source.SetCapability(twain.CAP_DUPLEXENABLED, twain.TWTY_BOOL, False)
        except Exception:
            pass

        logger.info("🖼️ Modo Flatbed: usando el cristal (intentando forzar)")

    # Si duplex está pedido pero estamos en flatbed, lo desactivamos
    if duplex and not feeder:
        logger.warning("⚠ Dúplex no disponible en flatbed — se ignora duplex para este escaneo.")
        duplex = False

    # intentar activar dúplex solo si feeder==True
    if duplex and feeder:
        try:
            source.SetCapability(twain.CAP_DUPLEXENABLED, twain.TWTY_BOOL, True)
        except Exception:
            logger.warning("⚠ Advertencia: no se pudo activar dúplex")

    # --- Intentos de RequestAcquire (fallbacks) ---
    def try_request_acquire(show_ui, modal):
        """Intenta RequestAcquire y devuelve (success, exception_or_none)."""
        try:
            # ligero retardo para que el driver procese cambios de capability
            time.sleep(0.2)
            source.RequestAcquire(show_ui, modal)
            return True, None
        except Exception as e:
            return False, e

    # Primero intentamos sin UI (silencioso). Si falla, intentamos con UI visible.
    ok, err = try_request_acquire(0, 0)
    if not ok:
        logger.warning(f"⚠ RequestAcquire silencioso falló: {err}; intentando mostrar UI del driver (fallback).")
        ok_ui, err_ui = try_request_acquire(1, 0)  # show UI non-modal
        if not ok_ui:
            logger.warning(f"⚠ RequestAcquire con UI también falló: {err_ui}. Intentando último intento modal...")
            ok_modal, err_modal = try_request_acquire(1, 1)  # modal UI
            if not ok_modal:
                _safe_destroy(source, sm)
                raise TwainScanError(
                    "No se pudo iniciar adquisición (intentos sin UI/UI/modal fallaron). "
                    f"Último error: {err_modal}"
                )

    # --- Transferencia / procesamiento de imágenes ---
    images = []

    # Si estamos en flatbed, solo hacemos un único XferImageNatively y analizamos la imagen
    if not feeder:
        try:
            info = source.XferImageNatively()
        except Exception as e:
            _safe_destroy(source, sm)
            raise TwainScanError(f"Error al transferir imagen desde flatbed: {e}")

        if not info:
            _safe_destroy(source, sm)
            raise TwainScanError("No se pudo transferir la imagen desde el flatbed (info vacía).")

        handle = info[0]
        filename = os.path.join(session_folder, "temp_flatbed.bmp")  # CAMBIO: usa la carpeta de sesión actual
        try:
            twain.DIBToBMFile(handle, filename)
        except Exception as e:
            _safe_destroy(source, sm)
            raise TwainScanError(f"Error al convertir DIB a archivo BMP: {e}")
        
        _safe_destroy(source, sm)

        with Image.open(filename) as img_opened:
            img_opened.load()  # forzar carga completa
            img = img_opened.copy()


        # aplicar rotación si corresponde
        if rotation != "off":
            if rotation == "right90":
                img = img.rotate(-90, expand=True)
            elif rotation == "180":
                img = img.rotate(180, expand=True)
            elif rotation == "left90":
                img = img.rotate(90, expand=True)

        if is_blank_page(img, content_threshold=0.015):  # 1.5% para flatbed
            try:
                os.remove(filename)
            except Exception:
                pass

            # Eliminar solo la carpeta de la sesión actual
            if session_id:
                try:
                    session_path = os.path.join(SCAN_FOLDER, session_id)
                    if os.path.exists(session_path):
                        shutil.rmtree(session_path)
                        logger.info(f"🧹 Carpeta de sesión '{session_path}' eliminada (hoja en blanco).")
                except Exception as e:
                    logger.warning(f"⚠ Error al eliminar carpeta de sesión: {e}")
            else:
                logger.warning("⚠ No hay session_id, no se eliminó ninguna carpeta.")
            raise TwainScanError("🚫 La primera hoja del cristal está en blanco. Escaneo cancelado y carpeta eliminada.")

        # Guardar la imagen escaneada en el formato configurado
        save_result = file_manager.save_page(img, color_mode=color_mode)
        try:
            os.remove(filename)
        except Exception:
            pass
        if not save_result["success"]:
            raise TwainScanError(f"Error al guardar la imagen del cristal: {save_result['error']}")
        try:
            img.close()
        except:
            pass
        return [save_result["full_path"]]

# --- Modo alimentador (ADF): loop normal para varias páginas ---
    else:
        # file_manager ya está sincronizado y se reutiliza
        page_number = 1
        images = []

        while True:
            try:
                feeder_loaded = source.GetCapability(twain.CAP_FEEDERLOADED)
                if feeder_loaded and not feeder_loaded[1]:
                    logger.info("📭 Alimentador vacío. Finalizando escaneo.")
                    break
            except Exception:
                pass

            try:
                info = source.XferImageNatively()
            except Exception as e:
                logger.error(f"⚠ Error al transferir imagen desde ADF: {e}")
                break

            if not info:
                break

            handle = info[0]
            filename = os.path.join(session_folder, f"temp_scan_{page_number}.bmp")
            try:
                twain.DIBToBMFile(handle, filename)
            except Exception as e:
                logger.error(f"⚠ Error al crear BMP temporal: {e}")
                break

            with Image.open(filename) as img_opened:
                img_opened.load()
                img = img_opened.copy()
            # Ahora filename está cerrado y se puede eliminar
            try:
                os.remove(filename)
            except:
                pass

            # Aplicar rotación si corresponde
            if rotation != "off":
                if rotation == "right90":
                    img = img.rotate(-90, expand=True)
                elif rotation == "180":
                    img = img.rotate(180, expand=True)
                elif rotation == "left90":
                    img = img.rotate(90, expand=True)
                    
            is_blank = is_blank_page(img, content_threshold=0.01)  # 1% para feeder
            if is_blank and skip_blank_pages:
                logger.info("⏭️ Página en blanco omitida según configuración.")
                try:
                    img.close()
                except:
                    pass
                continue

            # Guardar la página escaneada en el formato configurado
            save_result = file_manager.save_page(img, color_mode=color_mode)
            if save_result["success"]:
                logger.info(f"📄 Página {save_result['page_number']} guardada: {save_result['filename']}")
            else:
                logger.error(f"⚠ Error al guardar página {page_number}: {save_result['error']}")

            images.append(img)
            try:
                img.close()
            except:
                pass
            page_number += 1

        # Cerrar fuentes TWAIN
        _safe_destroy(source, sm)

        # Si no se escanearon imágenes válidas
        if not images:
            raise Exception("No se generaron imágenes o todas estaban en blanco.")

        return images

_twain_hardware_lock = threading.Lock()


def _run_twain_operation(func, timeout, operation_name="twain_op", scan_started_event=None, phase_timeout=None):
    """
    Ejecuta una operación TWAIN con timeout bifásico (conexión + escaneo).
    
    Timeout bifásico para cristal:
    - Fase 1: Espera inicial (phase_timeout) para que el hardware responda
    - Fase 2: Si scan_started_event se activa, cambia a timeout largo (timeout)
    
    Args:
        func: Función sin argumentos que ejecuta la operación TWAIN
        timeout: Segundos máximos de espera en fase de escaneo
        operation_name: Nombre para logging/debug
        scan_started_event: threading.Event que se activa cuando el escaneo realmente inició
        phase_timeout: Timeout de fase de conexión (si None, usa timeout normal)
    
    Returns:
        dict: Resultado de la operación o error con timeout=True
    """
    # Intentar obtener el lock del hardware (máximo 4 segundos)
    if not _twain_hardware_lock.acquire(blocking=True, timeout=4):
        logger.warning(f"[{operation_name}] Hardware TWAIN ocupado, no se pudo obtener lock en 4s")
        return {
            "success": False,
            "timeout": True,
            "message": "El escáner está ocupado por otra operación. Intente nuevamente."
        }
    
    # Crear executor NUEVO para esta operación (aislamiento de hilos zombie)
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=operation_name)
    try:
        future = executor.submit(func)
        
        # Si hay timeout bifásico (solo para cristal)
        if scan_started_event is not None and phase_timeout is not None:
            # FASE 1: Esperar a que inicie el escaneo (timeout corto)
            logger.debug(f"[{operation_name}] Fase 1: Esperando conexión ({phase_timeout}s)...")
            
            # Esperar a que el evento se active o timeout de fase 1
            if scan_started_event.wait(timeout=phase_timeout):
                # Escaneo iniciado, cambiar a FASE 2 (timeout largo)
                logger.info(f"[{operation_name}] ✅ Escaneo iniciado, cambiando a Fase 2 (timeout {timeout}s)")
                try:
                    result = future.result(timeout=timeout)
                    return result if result else {"success": False, "message": "Operación retornó None"}
                except FutureTimeoutError:
                    # Timeout en fase 2 (muy raro, escaneo muy lento)
                    logger.warning(f"⏱️ Timeout en Fase 2 de {operation_name} ({timeout}s) - escaneo muy lento")
                    return {
                        "success": False,
                        "timeout": True,
                        "message": f"Escaneo iniciado pero excedió tiempo máximo ({timeout}s)."
                    }
            else:
                # ❌ Timeout en fase 1 (no hay conexión)
                logger.warning(f"⏱️ Timeout en Fase 1 de {operation_name} ({phase_timeout}s) - sin conexión")
                future.cancel()  # Cancelar el future si aún está pendiente
                return {
                    "success": False,
                    "timeout": True,
                    "message": f"Sin conexión con el escáner ({phase_timeout}s). Verifique que esté encendido."
                }
        else:
            # Timeout simple (para check_feeder, check_flatbed_sheet, etc.)
            result = future.result(timeout=timeout)
            return result if result else {"success": False, "message": "Operación retornó None"}
            
    except FutureTimeoutError:
        logger.warning(f"⏱️ Timeout en {operation_name} ({timeout}s)")
        return {
            "success": False,
            "timeout": True,
            "message": f"Tiempo agotado ({timeout}s). Verifique la conexión del escáner."
        }
    except Exception as e:
        logger.exception(f"❌ Error inesperado en {operation_name}")
        return {"success": False, "message": f"Error inesperado: {str(e)}"}
    finally:
        # SIEMPRE liberar lock y terminar executor (incluso con timeout)
        _twain_hardware_lock.release()
        # shutdown(wait=False) permite que el hilo zombie muera solo, 
        # sin bloquear el servidor Flask
        executor.shutdown(wait=False)

def check_feeder(scanner_name=None, allow_fallback=True):
    """
    Verifica si hay papel en el alimentador del escáner.
    Retorna un diccionario con success y message.
    """
    def _build_check_for_candidate(candidate):
        def _check_internal():
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            sm = None
            source = None
            try:
                sm = twain.SourceManager(hwnd)
                scanners = sm.GetSourceList() or []
                if candidate not in scanners:
                    return {
                        "success": False,
                        "message": f"Escáner '{candidate}' no disponible en el sistema.",
                        "scanner_name": candidate
                    }

                source = sm.OpenSource(candidate)
                feeder_status = source.GetCapability(twain.CAP_FEEDERLOADED)

                if feeder_status and feeder_status[1]:
                    return {
                        "success": True,
                        "message": "✅ Hay papel en el alimentador.",
                        "scanner_name": candidate
                    }
                return {
                    "success": False,
                    "message": "⚠ No hay papel en el alimentador.",
                    "scanner_name": candidate
                }
            except Exception as e:
                return {
                    "success": False,
                    "message": f"Error al verificar alimentador: {str(e)}",
                    "scanner_name": candidate
                }
            finally:
                _safe_destroy(source, sm)

        return _check_internal

    candidates = _iter_scanner_candidates(
        preferred_scanner=scanner_name,
        allow_fallback=allow_fallback
    )
    if not candidates:
        return {
            "success": False,
            "message": "No hay escáneres candidatos configurados para verificar alimentador.",
            "timeout": False
        }

    attempted = []
    last_result = None
    for idx, candidate in enumerate(candidates):
        result = _run_twain_operation(
            _build_check_for_candidate(candidate),
            timeout=7,
            operation_name=f"check_feeder_{idx + 1}"
        )
        if not isinstance(result, dict):
            result = {
                "success": False,
                "message": "Resultado inválido al verificar alimentador.",
                "scanner_name": candidate
            }

        result.setdefault("scanner_name", candidate)
        attempted.append(candidate)

        if result.get("success"):
            result["attempted_scanners"] = attempted
            return result

        last_result = result
        if not allow_fallback:
            break

    if last_result is None:
        return {
            "success": False,
            "message": "No se pudo verificar alimentador en los escáneres configurados.",
            "attempted_scanners": attempted
        }

    last_result["attempted_scanners"] = attempted
    return last_result

def check_flatbed_sheet(scanner_name=None, allow_fallback=True):
    """
    Verifica si hay una hoja colocada en el cristal (flatbed).
    Si no puede detectarla automáticamente, realiza un escaneo rápido
    y analiza si la imagen está en blanco.
    """
    def _check_internal():
        hwnd = ctypes.windll.user32.GetForegroundWindow()
    
        logger.info("🕐 Verificando si hay hoja en el cristal...")
    
        try:
            sm = twain.SourceManager(hwnd)
            scanners = sm.GetSourceList()
            source, selected_scanner = _open_source_with_fallback(
                sm,
                scanners,
                preferred_scanner=scanner_name,
                allow_fallback=allow_fallback
            )
    
            # Desactivar alimentador para forzar modo flatbed
            try:
                source.SetCapability(twain.CAP_FEEDERENABLED, twain.TWTY_BOOL, False)
            except Exception:
                pass
            
            sheet_cap = getattr(twain, "CAP_SHEETDETECTOR", None)
            if sheet_cap is not None:
                try:
                    sheet_detector = source.GetCapability(sheet_cap)
                    if sheet_detector is not None:
                        has_sheet = sheet_detector[1] if len(sheet_detector) > 1 else False
                        if not has_sheet:
                            _safe_destroy(source, sm)
                            return {
                                "success": False,
                                "message": "⚠ No hay hoja en el cristal. Coloque una hoja y vuelva a intentar.",
                                "scanner_name": selected_scanner
                            }
                        _safe_destroy(source, sm)
                        return {
                            "success": True,
                            "message": "✅ Se detectó hoja en el cristal.",
                            "scanner_name": selected_scanner
                        }
                except Exception:
                    logger.warning("⚠ Error leyendo CAP_SHEETDETECTOR; se hará escaneo de prueba...")
            else:
                logger.warning("⚠ El escáner no expone CAP_SHEETDETECTOR. Se hará escaneo de prueba...")
    
    
            # Escaneo rápido de prueba (análisis de imagen blanca)
            try:
                source.RequestAcquire(0, 0)
                info = source.XferImageNatively()
                if info:
                    handle = info[0]
                    filename = os.path.join(SCAN_FOLDER, "temp_check_flatbed.bmp")
                    twain.DIBToBMFile(handle, filename)
    
                    with Image.open(filename) as img:
                        img.load()
                        is_blank = is_blank_page(img, content_threshold=0.015)  # 1.5% para flatbed
                    
                    try:
                        os.remove(filename)
                    except:
                        pass
                    
                    if is_blank:
                        _safe_destroy(source, sm)
                        return {
                            "success": False,
                            "message": "⚠ No se detectó hoja en el cristal. Coloque una hoja e intente nuevamente.",
                            "scanner_name": selected_scanner
                        }
                    _safe_destroy(source, sm)
                    return {
                        "success": True,
                        "message": "✅ Hoja detectada correctamente en el cristal.",
                        "scanner_name": selected_scanner
                    }
    
            except Exception as e:
                logger.warning(f"Advertencia al hacer escaneo de prueba: {e}")
    
            _safe_destroy(source, sm)
            return {
                "success": True,
                "message": "⚠ No se pudo verificar hoja automáticamente. Se continuará con el escaneo.",
                "scanner_name": selected_scanner
            }
    
        except Exception as e:
            return {"success": False, "message": f"Error al verificar cristal: {str(e)}"}
    
    return _run_twain_operation(_check_internal, timeout=21, operation_name="check_flatbed_sheet")

def validate_and_scan_flatbed(session_id, file_manager, dpi=300, color_mode="Text",
                            page_size="LT-R", rotation="off", timeout=None,
                            scanner_name=None, allow_fallback=True):
    """
    Escanea el cristal una sola vez, valida y guarda inmediatamente.
    
    Optimización: evita doble escaneo (check_flatbed_sheet + scan_document).
    
    Args:
        session_id: ID de sesión (con/sin prefijo 'session_')
        file_manager: Instancia de ScanFileManager
        dpi (int): Resolución (300, 400, 600)
        color_mode (str): "Text", "Gray", "Color", "Text/Photo"
        page_size (str): "LT-R", "A4-R", "13-LG", "A5-R"
        rotation (str): "off", "right90", "180", "left90", "auto"
        timeout (int): Tiempo máximo de espera en segundos
    
    Returns:
        dict: {'success': bool, 'message': str}
            Campos opcionales: 'blank_page', 'timeout', 'save_error', 
            'image_saved', 'page_number', 'filename'
    """
    # Crear event para señalizar cuando el escaneo realmente inició
    scan_started_event = threading.Event()
    
    def _scan_flatbed_internal():
        """Función interna para escanear flatbed (para usar con timeout bifásico)."""
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        source = None
        sm = None

        try:
            sm = twain.SourceManager(hwnd)
            scanners = sm.GetSourceList()
            source, selected_scanner = _open_source_with_fallback(
                sm,
                scanners,
                preferred_scanner=scanner_name,
                allow_fallback=allow_fallback
            )

            # Configurar modo flatbed (desactivar feeder)
            try:
                source.SetCapability(twain.CAP_FEEDERENABLED, twain.TWTY_BOOL, False)
                source.SetCapability(twain.CAP_AUTOFEED, twain.TWTY_BOOL, False)
                source.SetCapability(twain.CAP_DUPLEXENABLED, twain.TWTY_BOOL, False)
            except Exception as e:
                logger.warning(f"⚠ Advertencia configurando flatbed: {e}")

            # Configurar resolución
            try:
                source.SetCapability(twain.ICAP_XRESOLUTION, twain.TWTY_FIX32, dpi)
                source.SetCapability(twain.ICAP_YRESOLUTION, twain.TWTY_FIX32, dpi)
            except Exception as e:
                logger.warning(f"⚠ Advertencia configurando DPI: {e}")

            # Configurar modo de color
            pixel_types = {
                "Text": twain.TWPT_BW,
                "Gray": twain.TWPT_GRAY,
                "Color": twain.TWPT_RGB,
                "Text/Photo": twain.TWPT_RGB
            }
            try:
                source.SetCapability(
                    twain.ICAP_PIXELTYPE, 
                    twain.TWTY_UINT16, 
                    pixel_types.get(color_mode, twain.TWPT_RGB)
                )
            except Exception as e:
                logger.warning(f"⚠ Advertencia configurando modo de color: {e}")

            # Configurar tamaño de página
            size_mapping = {
                "LT-R": twain.TWSS_USLETTER,
                "A4-R": twain.TWSS_A4,
                "13-LG": twain.TWSS_USLEGAL,
                "A5-R": twain.TWSS_A5,
            }
            try:
                twain_size = size_mapping.get(page_size, twain.TWSS_A4)
                source.SetCapability(twain.ICAP_SUPPORTEDSIZES, twain.TWTY_UINT16, twain_size)
            except Exception as e:
                logger.warning(f"⚠ Advertencia configurando tamaño: {e}")

            # Iniciar adquisición
            try:
                source.RequestAcquire(0, 0)  # Sin UI
            except Exception as e:
                _safe_destroy(source, sm)
                return {
                    "success": False,
                    "message": f"Error al iniciar adquisición: {str(e)}"
                }
            
            # SEÑALIZAR: El hardware respondió y está listo para transferir
            # Esto marca el inicio real del escaneo (fin de Fase 1)
            scan_started_event.set()
            logger.debug("🟢 Escaneo iniciado - hardware respondiendo")

            # Transferir imagen (ahora en Fase 2 con timeout largo)
            info = source.XferImageNatively()
            if not info:
                _safe_destroy(source, sm)
                return {
                    "success": False,
                    "message": "No se pudo capturar imagen desde el cristal"
                }

            # Convertir DIB a archivo temporal
            handle = info[0]
            session_normalized = session_id if session_id.startswith("session_") else f"session_{session_id}"
            temp_file = os.path.join(SCAN_FOLDER, session_normalized, "temp_validate.bmp")

            try:
                twain.DIBToBMFile(handle, temp_file)
            except Exception as e:
                _safe_destroy(source, sm)
                return {
                    "success": False,
                    "message": f"Error al convertir imagen: {str(e)}"
                }

            # Cerrar recursos TWAIN antes de procesar imagen
            _safe_destroy(source, sm)

            # 1: usar context manager para cerrar automáticamente
            try:
                with Image.open(temp_file) as img:
                    # Forzar carga completa en memoria
                    img.load()
                    # Crear copia independiente (sin file handle)
                    img_copy = img.copy()
                # ← AL SALIR DEL 'with', PIL cierra el archivo automáticamente
                
                # CAMBIO 2: Ahora SÍ podemos eliminar el temp (archivo cerrado)
                try:
                    os.remove(temp_file)
                except PermissionError:
                    # Si falla, forzar garbage collection y reintentar
                    gc.collect()
                    time.sleep(0.3)
                    try:
                        os.remove(temp_file)
                    except Exception as e:
                        logger.warning(f"⚠️ No se pudo eliminar {temp_file}: {e}")
                except Exception:
                    pass
                
            except Exception as e:
                return {
                    "success": False,
                    "message": f"Error al procesar imagen: {str(e)}"
                }
            
            # CAMBIO 3: Trabajar con img_copy (sin handles abiertos)
            # Validar si está en blanco
            if is_blank_page(img_copy, content_threshold=0.015):  # 1.5% para flatbed
                # CAMBIO 4: Cerrar imagen antes de retornar
                try:
                    img_copy.close()
                    del img_copy
                except:
                    pass
                gc.collect()
                
                return {
                    "success": False,
                    "blank_page": True,
                    "message": "🚫 Hoja en blanco detectada en cristal"
                }

            # Aplicar rotación si es necesario
            if rotation != "off" and rotation != "auto":
                if rotation == "right90":
                    img_copy = img_copy.rotate(-90, expand=True)
                elif rotation == "180":
                    img_copy = img_copy.rotate(180, expand=True)
                elif rotation == "left90":
                    img_copy = img_copy.rotate(90, expand=True)
            elif rotation == "auto":
                # Auto-rotación se aplicará después en _perform_scan si es necesario
                pass
            
            # CAMBIO 5: Guardar y cerrar inmediatamente
            save_result = file_manager.save_page(img_copy, color_mode=color_mode)
            
            # CAMBIO 6: Liberar memoria explícitamente
            try:
                img_copy.close()
                del img_copy
            except:
                pass
            gc.collect()

            if save_result["success"]:
                return {
                    "success": True,
                    "blank_page": False,
                    "image_saved": True,
                    "page_number": save_result["page_number"],
                    "filename": save_result["filename"],
                    "scanner_name": selected_scanner,
                    "message": f"✅ Página {save_result['page_number']} guardada desde cristal"
                }
            else:
                return {
                    "success": False,
                    "message": f"Error al guardar imagen: {save_result.get('error', 'Desconocido')}"
                }

        except Exception as e:
            # CAMBIO 7: Limpiar recursos en caso de error
            _safe_destroy(source, sm)
            
            try:
                if 'img_copy' in locals():
                    img_copy.close()
                    del img_copy
                if 'img' in locals():
                    img.close()
                    del img
            except:
                pass
            
            gc.collect()
            
            error_msg = str(e).lower()
            is_timeout = any(word in error_msg for word in ['timeout', 'time out', 'timed out'])
            
            return {
                "success": False,
                "timeout": is_timeout,
                "message": f"Error inesperado durante escaneo: {str(e)}"
            }

    # Importar configuraciones de timeout
    from config.config import FLATBED_CONNECTION_TIMEOUT, FLATBED_SCAN_TIMEOUT
    
    # Usar timeout bifásico: Fase 1 (conexión) + Fase 2 (escaneo)
    return _run_twain_operation(
        _scan_flatbed_internal, 
        timeout=FLATBED_SCAN_TIMEOUT,           # Fase 2: escaneo activo (300s)
        operation_name="validate_flatbed",
        scan_started_event=scan_started_event,  # Event para detectar inicio
        phase_timeout=FLATBED_CONNECTION_TIMEOUT # Fase 1: conexión (8s)
    )