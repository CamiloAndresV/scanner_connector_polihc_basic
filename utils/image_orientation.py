"""
Utilidad para detectar y corregir orientación de imágenes escaneadas.
"""
import logging
from PIL import Image
import pytesseract
import os

from config.settings import settings

logger = logging.getLogger(__name__)

# Intentar variable de entorno primero
tesseract_path = settings.tesseract_cmd

if tesseract_path and os.path.exists(tesseract_path):
    pytesseract.pytesseract.tesseract_cmd = tesseract_path
    logger.info(f"Tesseract configurado en: {tesseract_path}")
elif os.path.exists(r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe'):
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe'
else:
    logger.warning("Tesseract no encontrado. Auto-rotación podría fallar.")

def detect_orientation(image_path, min_text_chars=100):
    """
    Detecta orientación de imagen usando Tesseract OCR.
    
    Args:
        image_path (str): Ruta al archivo
        min_text_chars (int): Mínimo de caracteres para confiar en detección (default: 100)
        
    Returns:
        dict: {'angle': int, 'confidence': float, 'needs_rotation': bool, 'text_length': int}
              Campos opcionales: 'reason' (si poco texto) o 'error' (si falla)
    """
    try:
        with Image.open(image_path) as image:
            # Verificar si hay suficiente texto
            text = pytesseract.image_to_string(image)
            text_length = len(text.strip())
            
            if text_length < min_text_chars:
                logger.warning(f"Muy poco texto ({text_length} chars). No se puede detectar orientación confiable.")
                return {
                    'angle': 0,
                    'confidence': 0,
                    'needs_rotation': False,
                    'reason': f'Insufficient text ({text_length} chars < {min_text_chars} required)'
                }

            # Tesseract detecta orientación
            osd = pytesseract.image_to_osd(image)

            # Parsear resultado
            angle = 0
            confidence = 0

            for line in osd.split('\n'):
                if 'Rotate:' in line:
                    angle = int(line.split(':')[1].strip())
                elif 'Orientation confidence:' in line:
                    confidence = float(line.split(':')[1].strip())

            needs_rotation = angle != 0 and confidence > 1.5  # Umbral de confianza

            logger.info(f"📊 Orientación detectada: {angle}° (confianza: {confidence:.1f}, texto: {text_length} chars)")

            return {
                'angle': angle,
                'confidence': confidence,
                'needs_rotation': needs_rotation,
                'text_length': text_length
            }
            
    except Exception as e:
        logger.warning(f"Error detectando orientación: {e}")
        return {
            'angle': 0,
            'confidence': 0,
            'needs_rotation': False,
            'error': str(e)
        }

def auto_rotate_image(image_path, save_path=None):
    """
    Detecta y corrige orientación de imagen usando Tesseract OCR.
    
    Args:
        image_path (str): Ruta al archivo original
        save_path (str, optional): Ruta de salida (None = sobrescribir)
        
    Returns:
        dict: {'success': bool, 'rotated': bool, 'angle': int, 
               'applied_rotation': int, 'confidence': float, 'output_path': str}
               O {'success': False, 'error': str} si falla
    """
    try:
        # Detectar orientación
        orientation = detect_orientation(image_path)
        
        if not orientation['needs_rotation']:
            return {
                'success': True,
                'rotated': False,
                'angle': 0,
                'output_path': image_path,
                'message': orientation.get('reason', 'Sin rotación necesaria')
            }
        
        # Cargar y rotar imagen
        with Image.open(image_path) as image:
            angle = orientation['angle']
            rotate_map = {90: -90, 180: -180, 270: -270}
            rotation_angle = rotate_map.get(angle, 0)
            rotated = image.rotate(rotation_angle, expand=True)
            dpi = image.info.get('dpi', (300, 300))
        
        # FUERA del context para evitar "closed file"
        output = save_path if save_path else image_path
        rotated.save(output, 'PNG', dpi=dpi)
        rotated.close()  # ← Cerrar explícitamente
        
        logger.info(f"Imagen rotada {angle}° → aplicando {rotation_angle}° y guardada en {output}")
        
        return {
            'success': True,
            'rotated': True,
            'angle': angle,
            'applied_rotation': rotation_angle,
            'confidence': orientation['confidence'],
            'output_path': output
        }
        
    except Exception as e:
        logger.error(f"Error rotando imagen: {e}")
        return {
            'success': False,
            'rotated': False,
            'error': str(e)
        }