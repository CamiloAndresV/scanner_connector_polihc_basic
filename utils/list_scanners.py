# utils/list_scanners.py

"""
Módulo para listar escáneres TWAIN disponibles en el sistema.

Requiere:
- Drivers TWAIN instalados
- Python de la misma arquitectura que el driver (generalmente 32-bit)

Solo verifica disponibilidad del driver, no funcionalidad del escáner.
"""

# 1. Standard library imports
import ctypes
import logging
from typing import List
import argparse

# 2. Third party imports
import twain

logger = logging.getLogger(__name__)

def get_hwnd(mode: str = "foreground") -> int:
    """
    Devuelve un HWND válido para TWAIN.
    mode: 'foreground' | 'desktop' | 'none'
    """
    try:
        if mode == "foreground":
            return ctypes.windll.user32.GetForegroundWindow()
        if mode == "desktop":
            return ctypes.windll.user32.GetDesktopWindow()
        return 0  # none
    except Exception:
        return 0

def list_scanners(hwnd_mode: str = "foreground") -> List[str]:
    """
    Retorna la lista de fuentes TWAIN disponibles.
    """
    hwnd = get_hwnd(hwnd_mode)
    sm = None
    try:
        sm = twain.SourceManager(hwnd)
        scanners = sm.GetSourceList() or []
        return scanners
    finally:
        try:
            if sm is not None:
                sm.destroy() # Liberar recursos del SourceManager despues de usarlo
        except Exception:
            # No interrumpir el flujo si falla la destrucción
            logger.debug("Fallo al destruir SourceManager", exc_info=True)


def main():
    """
    Punto de entrada principal para listar escáneres TWAIN disponibles.
    """
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description="Lista escáneres TWAIN disponibles")
    parser.add_argument("--hwnd", choices=["foreground", "desktop", "none"], default="foreground",
        help="Modo de HWND para inicializar TWAIN SourceManager")
    args = parser.parse_args() 

    try:
        scanners = list_scanners(args.hwnd)
        if scanners:
            logger.info("Escáneres 'TWAIN' encontrados:")
            for i, name in enumerate(scanners, start=1):
                logger.info("%d. %s", i, name)
        else:
            logger.info("No se encontraron escáneres TWAIN disponibles.")
            logger.info("Sugerencias: verificar drivers TWAIN, encender escáner, arquitectura Python/driver.")
    except Exception as e:
        # twain puede lanzar diferentes tipos de excepciones según la implementación
        logger.error("Error al listar escáneres: %s", e, exc_info=True)

# Punto de entrada del script
if __name__ == "__main__":
    main()
