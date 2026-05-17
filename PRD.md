# Product Requirements Document (PRD)
## Scanner Connector POLIHC

**Versión:** 1.0  
**Fecha:** Diciembre 2025  
**Estado:** Fase 1 Completada - Fase 2 En Progreso

---

## 1. Resumen Ejecutivo

### 1.1 Visión del Producto
El **Scanner Connector POLIHC** es un sistema de escaneo de documentos estructurado en cuatro fases que permite digitalizar documentos físicos, procesarlos mediante OCR e IA, y almacenarlos de forma estructurada en una base de datos. Este PRD se enfoca principalmente en las **Fases 1 y 2: Conector Local (Flask) e Integración con Django**, que actúan como intermediario entre el hardware del escáner y la aplicación web Django.

### 1.2 Objetivo Principal
Proporcionar una API REST robusta y confiable que permita a una aplicación web Django controlar remotamente un escáner físico (Toshiba e-Studio 2822AM) mediante el protocolo TWAIN, gestionando sesiones de escaneo, entregando imágenes de alta calidad y garantizando la disponibilidad del hardware.

### 1.3 Alcance del Proyecto
- **Incluye:**
  - API REST Flask para control de escáner
  - Gestión de sesiones con bloqueo exclusivo
  - Verificación de disponibilidad del hardware
  - Entrega de imágenes WEBP (por defecto) o PNG (legacy)
  - Limpieza automática de recursos temporales
  - Integración con protocolo TWAIN 32-bit

- **No incluye:**
  - Interfaz de usuario web (responsabilidad de Django - Fase 2)
  - Generación de PDFs (responsabilidad de Django - Fase 2)
  - Procesamiento OCR/IA (Fase 3)
  - Almacenamiento permanente de documentos (Fase 3)

---

## 2. Contexto y Antecedentes

### 2.1 Problema a Resolver
Las organizaciones de salud requieren digitalizar grandes volúmenes de documentos físicos (historias clínicas, radiografías, formularios) para:
- Mejorar la accesibilidad de la información
- Reducir el espacio físico de almacenamiento
- Facilitar la búsqueda y recuperación de documentos
- Habilitar procesamiento automatizado mediante OCR e IA

El desafío técnico es conectar un escáner físico con una aplicación web moderna, manejando las limitaciones del protocolo TWAIN (solo 32-bit, solo Windows) y garantizando operaciones confiables.

### 2.2 Usuarios Objetivo
- **Usuarios finales:** Personal administrativo y clínico que escanea documentos
- **Administradores de sistema:** Personal técnico que instala y mantiene el conector
- **Desarrolladores:** Equipo que integra el conector con Django

### 2.3 Restricciones Técnicas
- **Python 32-bit obligatorio:** TWAIN solo funciona en arquitectura de 32 bits
- **Windows únicamente:** TWAIN no está disponible en Linux/macOS
- **Un escáner por instancia:** Cada instancia del conector controla un solo dispositivo físico
- **Sesión única:** Solo un usuario puede escanear a la vez por escáner

---

## 3. Requisitos Funcionales

### 3.1 Gestión de Sesiones de Escaneo

#### RF-001: Iniciar Sesión de Escaneo
**Prioridad:** Crítica  
**Descripción:** El sistema debe permitir iniciar una nueva sesión de escaneo con parámetros configurables.

**Criterios de Aceptación:**
- Endpoint: `POST /api/scan/start`
- Validar parámetros de entrada (DPI, modo de color, tamaño, rotación)
- Verificar disponibilidad del escáner antes de iniciar
- Crear carpeta única por sesión: `session_<timestamp>_<user_id>/`
- Adquirir bloqueo exclusivo del escáner (timeout: 20 minutos)
- Retornar `session_id` inmediatamente
- Verificar presencia de hojas en ADF o flatbed según configuración
- Responder con código HTTP 200 si éxito, 409 si escáner ocupado, 400 si parámetros inválidos

**Parámetros de Entrada:**
```json
{
  "user_id": "string (requerido)",
  "dpi": 300 | 400 | 600,
  "color_mode": "Text" | "Gray" | "Color" | "Text/Photo",
  "duplex": boolean,
  "feeder": boolean,
  "page_size": "LT-R" | "A4-R" | "13-LG" | "A5-R",
  "rotation": "off" | "right90" | "180" | "left90" | "auto",
  "skip_blank_pages": boolean
}
```

#### RF-002: Continuar Escaneo en Sesión Activa
**Prioridad:** Alta  
**Descripción:** Permitir agregar más páginas a una sesión existente sin cerrarla.

**Criterios de Aceptación:**
- Endpoint: `POST /api/scan/continue`
- Validar que la sesión existe y pertenece al usuario
- Mantener bloqueo del escáner
- Agregar nuevas páginas a la carpeta existente
- Continuar numeración de páginas desde la última escaneada

#### RF-003: Cancelar Escaneo
**Prioridad:** Alta  
**Descripción:** Cancelar un escaneo en progreso y eliminar todos los archivos temporales.

**Criterios de Aceptación:**
- Endpoint: `POST /api/scan/cancel`
- Detener proceso de escaneo si está en curso
- Eliminar carpeta de sesión completa
- Liberar bloqueo del escáner
- Responder con código 200

#### RF-004: Finalizar Sesión
**Prioridad:** Alta  
**Descripción:** Finalizar una sesión de escaneo y liberar recursos.

**Criterios de Aceptación:**
- Endpoint: `POST /api/scan/finish`
- Liberar bloqueo del escáner
- Mantener archivos hasta que Django los descargue
- Marcar sesión como completada

### 3.2 Verificación de Estado y Disponibilidad

#### RF-005: Verificar Disponibilidad del Escáner
**Prioridad:** Crítica  
**Descripción:** Verificar si el escáner está conectado, encendido y listo para usar.

**Criterios de Aceptación:**
- Endpoint: `GET /api/scan/check-scanner`
- Verificar conexión con hardware (timeout: 28 segundos máximo)
- Verificar presencia de hojas en ADF (timeout: 7 segundos)
- Verificar presencia de hojas en flatbed (timeout: 21 segundos)
- Responder con código 200 si disponible, 503 si no disponible, 504 si timeout
- No bloquear la API si el escáner está apagado

**Respuesta de Ejemplo:**
```json
{
  "success": true,
  "message": "Escáner conectado y listo",
  "feeder": {
    "success": true,
    "message": "✅ Hay papel en el alimentador."
  },
  "flatbed": {
    "success": false,
    "message": "⚠ No hay hoja en el cristal."
  }
}
```

#### RF-006: Verificar Estado del Escaneo
**Prioridad:** Alta  
**Descripción:** Obtener el estado actual de una sesión de escaneo en tiempo real.

**Criterios de Aceptación:**
- Endpoint: `GET /api/scan/status`
- Retornar estado: `idle`, `scanning`, `completed`, `error`, `cancelled`
- Incluir número de páginas escaneadas
- Incluir mensajes de progreso o error
- Responder inmediatamente sin bloquear

#### RF-007: Verificar Alimentador (ADF)
**Prioridad:** Media  
**Descripción:** Verificar específicamente si hay papel en la bandeja automática.

**Criterios de Aceptación:**
- Endpoint: `GET /api/scan/check-feeder`
- Timeout: 7 segundos
- Responder con código 200 si hay papel, 504 si timeout

### 3.3 Recuperación de Imágenes

#### RF-008: Listar Páginas de Sesión
**Prioridad:** Crítica  
**Descripción:** Obtener lista de todas las páginas escaneadas en una sesión.

**Criterios de Aceptación:**
- Endpoint: `GET /api/scan/pages` (sesión activa)
- Endpoint: `GET /api/scan/pages/<session_id>` (sesión específica)
- Retornar array con: `filename`, `page_number`, `full_path`
- Ordenar por número de página

**Respuesta de Ejemplo:**
```json
{
  "success": true,
  "session_id": "session_1730739456_usuario123",
  "pages": [
    {
      "filename": "page_001.webp",
      "page_number": 1,
      "full_path": "scans/session_1730739456_usuario123/page_001.webp"
    }
  ]
}
```

#### RF-009: Descargar Imagen (WEBP/PNG)
**Prioridad:** Crítica  
**Descripción:** Descargar una imagen WEBP (por defecto) o PNG (legacy) específica de una sesión.

**Criterios de Aceptación:**
- Endpoint: `GET /api/scan/download/<session_id>/<filename>`
- Validar que la sesión existe
- Validar que el archivo existe
- Retornar archivo WEBP/PNG con headers HTTP correctos
- Proteger contra path traversal attacks

### 3.4 Gestión de Archivos y Limpieza

#### RF-010: Limpieza Automática Programada
**Prioridad:** Alta  
**Descripción:** Eliminar automáticamente sesiones con más de 20 minutos de inactividad.

**Criterios de Aceptación:**
- Ejecutarse diariamente a las 15:30 (configurable)
- Eliminar carpetas de sesión con modificación > 20 minutos
- No eliminar sesiones activas en progreso
- Liberar locks de sesiones expiradas
- Registrar operaciones en logs

#### RF-011: Limpieza Manual
**Prioridad:** Media  
**Descripción:** Permitir ejecutar limpieza manual de sesiones residuales.

**Criterios de Aceptación:**
- Endpoint: `POST /api/scan/run-cleanup`
- Ejecutar en thread separado (no bloquear API)
- Retornar número de sesiones eliminadas
- Endpoint: `DELETE /api/scan/cleanup/<session_id>` para eliminar sesión específica

### 3.5 Procesamiento de Imágenes

#### RF-012: Detección de Páginas en Blanco
**Prioridad:** Media  
**Descripción:** Detectar y omitir automáticamente páginas en blanco durante el escaneo.

**Criterios de Aceptación:**
- Detectar si > 99% de píxeles son blancos
- Omitir páginas en blanco si `skip_blank_pages = true`
- Permitir máximo 2 páginas en blanco consecutivas antes de detener
- Configurable por sesión

#### RF-013: Rotación de Imágenes
**Prioridad:** Media  
**Descripción:** Aplicar rotación automática o manual a las imágenes escaneadas.

**Criterios de Aceptación:**
- Soportar: `off`, `right90`, `180`, `left90`, `auto`
- Aplicar rotación antes de guardar la imagen (WEBP/PNG)
- Modo `auto`: detectar orientación mediante OCR/IA (opcional)

#### RF-014: Formato de Salida (WEBP/PNG)
**Prioridad:** Crítica  
**Descripción:** Generar imágenes WEBP (por defecto) o PNG (legacy) con calidad configurable.

**Criterios de Aceptación:**
- Formato: WEBP por defecto (con compresión configurable) o PNG legacy
- Nomenclatura: `page_001.webp` (o `.png` si `SCAN_IMAGE_FORMAT=png`)
- Resolución: 300, 400 o 600 DPI según configuración
- Modos de color: Text, Gray, Color, Text/Photo

---

## 4. Requisitos No Funcionales

### 4.1 Rendimiento

#### RNF-001: Tiempos de Respuesta
- Endpoint `/check-scanner`: máximo 28 segundos (incluso si escáner apagado)
- Endpoint `/start`: respuesta inmediata (< 1 segundo) con `session_id`
- Endpoint `/status`: respuesta inmediata (< 100ms)
- Endpoint `/download`: streaming eficiente de archivos WEBP/PNG

#### RNF-002: Throughput
- Soportar escaneo continuo de hasta 50 páginas por sesión
- Procesar imágenes WEBP/PNG con calidad configurable
- Manejar múltiples solicitudes concurrentes (aunque solo una sesión activa)

### 4.2 Confiabilidad

#### RNF-003: Manejo de Errores
- Todos los endpoints deben retornar códigos HTTP apropiados
- Logs detallados de errores sin exponer información sensible
- Timeouts en todas las operaciones de hardware
- Recuperación automática de errores TWAIN

#### RNF-004: Disponibilidad
- El servicio debe iniciarse automáticamente al arrancar Windows
- Tolerancia a fallos: si el escáner se desconecta, el servicio sigue funcionando
- Reintentos automáticos en operaciones críticas

### 4.3 Seguridad

#### RNF-005: Autenticación y Autorización
- **Fase actual:** Sin autenticación (servicio local)
- **Futuro:** Implementar API keys o JWT para producción

#### RNF-006: Protección de Datos
- Validar y sanitizar todos los parámetros de entrada
- Proteger contra path traversal en endpoints de descarga
- No almacenar información sensible en logs
- Limpiar archivos temporales después de uso

#### RNF-007: CORS
- Configurar CORS para permitir solo orígenes autorizados (Django)
- Headers permitidos: `Content-Type`, `Authorization`

### 4.4 Mantenibilidad

#### RNF-008: Código Modular
- Estructura clara: `controllers/`, `services/`, `utils/`, `config/`
- Separación de responsabilidades
- Documentación inline con docstrings

#### RNF-009: Logging
- Usar `logging` module en lugar de `print()`
- Niveles configurables: DEBUG, INFO, WARNING, ERROR
- Logs estructurados (futuro: JSON)

#### RNF-010: Testing
- Pruebas unitarias para funciones críticas
- Pruebas de integración para flujos completos
- Cobertura mínima: 70% (objetivo)

### 4.5 Compatibilidad

#### RNF-011: Plataforma
- Windows 10/11 (64-bit)
- Python 3.13.7 (32-bit) - OBLIGATORIO
- TWAIN 32-bit driver instalado

#### RNF-012: Hardware
- Escáner Toshiba e-Studio 2822AM (o compatible)
- Soporte para ADF (alimentador automático) y flatbed (cristal)

### 4.6 Escalabilidad

#### RNF-013: Arquitectura
- Una instancia del conector por escáner físico
- Posibilidad de ejecutar múltiples instancias en diferentes equipos
- Sin estado compartido entre instancias

---

## 5. Arquitectura y Diseño

### 5.1 Arquitectura General

```
┌─────────────────┐
│  Django (Web)   │
│  Frontend + API │
└────────┬────────┘
         │ HTTP REST
         │ (localhost:8000)(solo local)
         ▼
┌─────────────────┐
│  Flask API      │  ← Scanner Connector (Este proyecto)
│  (Conector)     │
└────────┬────────┘
         │ TWAIN Protocol
         │ (32-bit, localhost:5000)
         ▼
┌─────────────────┐
│  Escáner Físico │
│  Toshiba 2822AM │
└─────────────────┘
```

**Nota:** Por decisión de la empresa, el sistema opera solo en modo local. No se usa Tailscale, VPS ni acceso remoto.

### 5.2 Estructura del Proyecto

```
scanner_connector_polihc_basic/
│
├── app.py                    # Punto de entrada Flask
├── README.md                 # Documentación de usuario
├── PRD.md                    # Este documento
├── requirements.txt          # Dependencias Python
├── context.txt              # Documentación técnica
│
├── config/
│   ├── config.py            # Parámetros de escaneo
│   └── settings.py          # Configuración Flask
│
├── controllers/
│   ├── scan_controller.py   # Endpoints de producción
│   └── test_controller.py   # Endpoints de desarrollo
│
├── services/
│   └── twain_connector.py   # Interfaz TWAIN
│
├── utils/
│   ├── file_manager.py      # Gestión de archivos WEBP/PNG
│   ├── session_lock.py      # Sistema de bloqueo
│   ├── cleanup_scheduler.py # Limpieza automática
│   ├── image_orientation.py  # Rotación de imágenes
│   └── list_scanners.py     # Listar escáneres
│
├── scans/                   # Carpeta temporal (gitignored)
│   └── session_*/          # Carpetas por sesión
│
└── test/                    # Pruebas unitarias
```

### 5.3 Flujo de Datos

#### Flujo de Escaneo Completo

```
1. Django → POST /api/scan/start
   ├─ Validar parámetros
   ├─ Verificar disponibilidad escáner
   ├─ Adquirir bloqueo de sesión
   └─ Retornar session_id

2. Flask → Escaneo en background thread
   ├─ Conectar con TWAIN
   ├─ Escanear páginas
   ├─ Detectar páginas en blanco
   ├─ Aplicar rotación
  └─ Guardar WEBP/PNG en carpeta de sesión

3. Django → GET /api/scan/status (polling)
   └─ Obtener progreso en tiempo real

4. Django → GET /api/scan/pages/{session_id}
   └─ Obtener lista de páginas escaneadas

5. Django → GET /api/scan/download/{session_id}/{filename}
  └─ Descargar cada imagen WEBP/PNG

6. Django → POST /api/scan/finish
   └─ Liberar recursos y bloqueo
```

### 5.4 Sistema de Bloqueo

**Objetivo:** Prevenir escaneos simultáneos en el mismo escáner.

**Implementación:**
- Lock basado en archivo: `scans/.lock`
- Timeout: 20 minutos por sesión
- Thread-safe usando `threading.Lock()`
- Liberación automática al finalizar/cancelar

**Estados:**
- `idle`: Sin sesión activa
- `scanning`: Escaneo en progreso
- `completed`: Escaneo finalizado (archivos disponibles)
- `error`: Error durante escaneo
- `cancelled`: Escaneo cancelado por usuario

---

## 6. Configuración y Parámetros

### 6.1 Parámetros de Escaneo

| Parámetro | Valores Permitidos | Valor por Defecto | Descripción |
|-----------|-------------------|-------------------|-------------|
| `dpi` | 300, 400, 600 | 300 | Resolución en puntos por pulgada |
| `color_mode` | Text, Gray, Color, Text/Photo | Text | Modo de escaneo de color |
| `duplex` | true, false | false | Escaneo a doble cara |
| `feeder` | true, false | true | true = ADF, false = Flatbed |
| `page_size` | LT-R, A4-R, 13-LG, A5-R | LT-R | Tamaño de página |
| `rotation` | off, right90, 180, left90, auto | off | Rotación de imagen |
| `skip_blank_pages` | true, false | true | Omitir páginas en blanco |

### 6.2 Tamaños de Página

| Código | Dimensiones (mm) | Descripción | TWAIN Code |
|--------|------------------|-------------|------------|
| LT-R | 216 x 279 | Carta (Letter) | TWSS_USLETTER |
| A4-R | 210 x 297 | A4 Portrait | TWSS_A4 |
| 13-LG | 216 x 330 | Oficio (Legal) | TWSS_USLEGAL |
| A5-R | 148 x 210 | A5 Portrait | TWSS_A5 |

### 6.3 Timeouts

| Operación | Timeout | Descripción |
|-----------|---------|-------------|
| Verificación ADF | 7 segundos | Detección de papel en bandeja |
| Verificación Flatbed | 21 segundos | Detección de hoja en cristal |
| Sesión de escaneo | 20 minutos | Duración máxima de sesión |
| Limpieza automática | 20 minutos | Inactividad para eliminar sesión |

### 6.4 Variables de Entorno

```bash
# .env (opcional)
DEBUG=false                    # Modo desarrollo/producción
LOG_LEVEL=INFO                 # DEBUG, INFO, WARNING, ERROR
SECRET_KEY=<clave_secreta>     # Clave para sesiones Flask
DJANGO_URL=http://localhost:8000  # URL de Django para CORS
SWAGGER_USER=admin            # Usuario para Swagger (solo desarrollo)
SWAGGER_PASSWORD=admin123     # Contraseña para Swagger (solo desarrollo)

# Imagenes (formato y compresion)
SCAN_IMAGE_FORMAT=webp
SCAN_IMAGE_QUALITY=85
SCAN_IMAGE_METHOD=4
SCAN_IMAGE_LOSSLESS=False
```

---

## 7. Integración con Django

### 7.1 Estrategia de Integración: Pull Strategy

Django controla el flujo completo mediante polling y descarga de imágenes.

**Ventajas:**
- Control total del flujo desde Django
- Manejo de errores más simple
- Reintentos automáticos si falla descarga
- Menos acoplamiento entre sistemas

### 7.2 Flujo de Integración Recomendado

```python
# Ejemplo en Django views.py
import requests
import time

def escanear_documento(request):
    # 1. Iniciar escaneo
    response = requests.post('http://localhost:5000/api/scan/start', json={
        'user_id': str(request.user.id),
        'feeder': True,
        'dpi': 300,
        'color_mode': 'Color',
        'page_size': 'A4-R'
    })
    
    if response.status_code != 200:
        return JsonResponse({'error': 'No se pudo iniciar escaneo'}, status=500)
    
    session_id = response.json()['session_id']
    
    # 2. Polling de estado (cada 2 segundos, máximo 2 minutos)
    for _ in range(60):
        status = requests.get('http://localhost:5000/api/scan/status').json()
        
        if status['progress']['status'] == 'completed':
            break
        elif status['progress']['status'] == 'error':
            return JsonResponse({'error': status['progress']['message']}, status=500)
        
        time.sleep(2)
    
    # 3. Obtener lista de páginas
    pages_response = requests.get(
        f'http://localhost:5000/api/scan/pages/{session_id}'
    )
    pages = pages_response.json()['pages']
    
    # 4. Descargar cada imagen
    for page in pages:
        filename = page['filename']
        img_url = f'http://localhost:5000/api/scan/download/{session_id}/{filename}'
        img_data = requests.get(img_url).content
        
        # Guardar en Django media folder
        with open(f'media/scans/{filename}', 'wb') as f:
            f.write(img_data)
    
    # 5. Finalizar sesión
    requests.post('http://localhost:5000/api/scan/finish')
    
    return JsonResponse({'success': True, 'imagenes': len(pages)})
```

### 7.3 Endpoints Requeridos por Django

| Endpoint | Uso en Django |
|----------|---------------|
| `POST /api/scan/start` | Iniciar nuevo escaneo |
| `GET /api/scan/status` | Verificar progreso (polling) |
| `GET /api/scan/pages/{session_id}` | Obtener lista de páginas |
| `GET /api/scan/download/{session_id}/{filename}` | Descargar cada imagen |
| `POST /api/scan/continue` | Agregar más páginas |
| `POST /api/scan/finish` | Finalizar y limpiar |
| `POST /api/scan/cancel` | Cancelar escaneo |

---

## 8. Casos de Uso

### 8.1 Caso de Uso 1: Escaneo Básico de Documento

**Actor:** Usuario final (vía Django)  
**Precondiciones:**
- Escáner conectado y encendido
- Papel en ADF o hoja en flatbed
- Conector Flask ejecutándose

**Flujo Principal:**
1. Usuario inicia escaneo desde interfaz Django
2. Django envía `POST /api/scan/start` con parámetros
3. Flask verifica disponibilidad del escáner
4. Flask inicia escaneo en background
5. Django hace polling con `GET /api/scan/status`
6. Cuando completado, Django descarga imágenes
7. Django finaliza sesión con `POST /api/scan/finish`

**Flujo Alternativo:**
- Si escáner ocupado: Django recibe 409, muestra mensaje al usuario
- Si error: Django recibe mensaje de error, permite reintentar

### 8.2 Caso de Uso 2: Escaneo por Lotes

**Actor:** Usuario final  
**Precondiciones:** Sesión activa iniciada

**Flujo Principal:**
1. Usuario escanea primer lote de páginas
2. Usuario decide "Escanear más páginas"
3. Django envía `POST /api/scan/continue`
4. Flask agrega nuevas páginas a la sesión existente
5. Repetir pasos 3-4 según necesidad
6. Usuario finaliza y Django descarga todas las páginas

### 8.3 Caso de Uso 3: Cancelación de Escaneo

**Actor:** Usuario final  
**Precondiciones:** Escaneo en progreso

**Flujo Principal:**
1. Usuario cancela desde interfaz Django
2. Django envía `POST /api/scan/cancel`
3. Flask detiene escaneo y elimina archivos temporales
4. Flask libera bloqueo del escáner
5. Django confirma cancelación al usuario

### 8.4 Caso de Uso 4: Verificación de Disponibilidad

**Actor:** Sistema Django  
**Precondiciones:** Ninguna

**Flujo Principal:**
1. Django verifica disponibilidad antes de mostrar opción de escaneo
2. Django envía `GET /api/scan/check-scanner`
3. Flask verifica hardware (con timeouts)
4. Flask retorna estado: disponible, no disponible, o timeout
5. Django muestra/oculta opción de escaneo según resultado

---

## 9. Métricas y KPIs

### 9.1 Métricas de Rendimiento

| Métrica | Objetivo | Medición |
|---------|----------|----------|
| Tiempo de respuesta `/check-scanner` | < 28 segundos | P95 |
| Tiempo de respuesta `/start` | < 1 segundo | P95 |
| Tiempo de respuesta `/status` | < 100ms | P95 |
| Tasa de éxito de escaneos | > 95% | Porcentaje |
| Tiempo promedio por página | < 10 segundos | Promedio |

### 9.2 Métricas de Confiabilidad

| Métrica | Objetivo | Medición |
|---------|----------|----------|
| Disponibilidad del servicio | > 99% | Uptime |
| Tasa de errores | < 2% | Porcentaje de requests |
| Sesiones completadas exitosamente | > 90% | Porcentaje |

### 9.3 Métricas de Uso

| Métrica | Descripción |
|---------|-------------|
| Número de sesiones por día | Volumen de uso |
| Páginas escaneadas por sesión | Promedio |
| Tiempo promedio de sesión | Duración |
| Tasa de cancelación | Porcentaje de cancelaciones |

---

## 10. Roadmap y Evolución

### 10.1 Fase 1: Conector Local (✅ Completada)

- [x] API REST Flask completa
- [x] Integración con TWAIN
- [x] Sistema de sesiones con bloqueo
- [x] Verificación de disponibilidad con timeouts
- [x] Limpieza automática programada
- [x] Documentación completa

### 10.2 Fase 2: Integración con Django (🔄 En Progreso)

- [x] Integración completa con aplicación Django
- [ ] Pruebas end-to-end (pendiente finalizar pruebas)
- [ ] Optimización de rendimiento (pendiente optimizar)
- [ ] Despliegue como servicio de Windows

**Estado actual:** La integración con Django está completa y funcional. Se requiere finalizar las pruebas de integración, optimizar el rendimiento y configurar el despliegue como servicio de Windows para producción.

### 10.3 Fase 3: Módulo OCR e Inteligencia Artificial (📋 Planificado)

- [ ] Integración con módulo OCR (Tesseract / Azure / AWS)
- [ ] Clasificación automática de documentos mediante IA
- [ ] Extracción de datos estructurados de documentos escaneados
- [ ] Almacenamiento y guardado de documentos en PostgreSQL
- [ ] Procesamiento de datos clínicos y estructurados

**Objetivo:** Completar el ciclo de digitalización con procesamiento inteligente de documentos y almacenamiento estructurado en base de datos.

### 10.4 Fase 4: Mejoras Técnicas y Optimizaciones (📅 Futuro)

- [ ] Métricas de rendimiento (Prometheus / Grafana)
- [ ] Soporte multi-escáner (múltiples instancias en red)
- [ ] Interfaz web de administración (🔄 En proceso con Django, casi listo)
- [ ] Pruebas unitarias automatizadas (cobertura > 70%)
- [ ] Logs estructurados (JSON)
- [ ] Autenticación JWT o API keys para producción
- [ ] CI/CD con GitHub Actions
- [ ] Contenedorización (Docker) si es necesario

**Objetivo:** Mejorar la robustez, escalabilidad y mantenibilidad del sistema con herramientas de monitoreo, pruebas automatizadas y mejoras de seguridad.

---

## 11. Riesgos y Mitigaciones

### 11.1 Riesgos Técnicos

| Riesgo | Impacto | Probabilidad | Mitigación |
|--------|---------|--------------|------------|
| Driver TWAIN incompatible | Alto | Media | Validar compatibilidad antes de despliegue |
| Memory leaks en TWAIN | Alto | Media | ✅ Resuelto: Context managers y gc.collect() |
| Bloqueos del protocolo TWAIN | Alto | Media | ✅ Resuelto: Timeouts con ThreadPoolExecutor |
| Python 32-bit difícil de instalar | Medio | Baja | Documentación detallada y scripts de instalación |
| Sesiones huérfanas consumen espacio | Medio | Media | ✅ Resuelto: Limpieza automática programada |

### 11.2 Riesgos Operacionales

| Riesgo | Impacto | Probabilidad | Mitigación |
|--------|---------|--------------|------------|
| Escáner desconectado durante uso | Alto | Media | Verificación previa y mensajes de error claros |
| Múltiples usuarios intentan escanear | Medio | Alta | ✅ Resuelto: Sistema de bloqueo exclusivo |
| Archivos temporales no se limpian | Medio | Baja | ✅ Resuelto: Limpieza automática y manual |
| Servicio no inicia automáticamente | Medio | Baja | Configurar como servicio de Windows |

### 11.3 Riesgos de Integración

| Riesgo | Impacto | Probabilidad | Mitigación |
|--------|---------|--------------|------------|
| Cambios en API de Django | Medio | Media | Versionado de API y documentación clara |
| Problemas de red local | Medio | Baja | Manejo de errores de conexión en Django |
| Incompatibilidad de formatos | Bajo | Baja | Estándar WEBP/PNG bien definido |

---

## 12. Criterios de Aceptación del Producto

### 12.1 Criterios Funcionales

- ✅ Todos los endpoints REST funcionan correctamente
- ✅ Sistema de bloqueo previene escaneos simultáneos
- ✅ Verificación de disponibilidad responde en < 28 segundos
- ✅ Imágenes WEBP/PNG se generan con calidad correcta
- ✅ Limpieza automática elimina sesiones expiradas
- ✅ Detección de páginas en blanco funciona correctamente

### 12.2 Criterios No Funcionales

- ✅ Servicio inicia sin errores
- ✅ Logs proporcionan información útil para debugging
- ✅ Código modular y mantenible
- ✅ Documentación completa (README, PRD, context.txt)
- ✅ Manejo robusto de errores y timeouts

### 12.3 Criterios de Integración

- ✅ Django puede iniciar escaneos exitosamente
- ✅ Django puede descargar imágenes correctamente
- ✅ Flujo completo end-to-end funciona sin errores
- ✅ Múltiples sesiones secuenciales funcionan correctamente

---

## 13. Glosario

- **ADF (Automatic Document Feeder):** Bandeja automática que alimenta hojas al escáner
- **Flatbed:** Cristal plano donde se coloca una hoja manualmente
- **TWAIN:** Protocolo estándar para comunicación con escáneres e impresoras
- **Session ID:** Identificador único de una sesión de escaneo
- **DPI (Dots Per Inch):** Resolución de escaneo en puntos por pulgada
- **Duplex:** Escaneo a doble cara (anverso y reverso)
- **WEBP:** Formato moderno con compresión configurable (lossy o lossless)
- **PNG (legacy):** Formato de imagen sin pérdida de calidad
- **Pull Strategy:** Estrategia donde Django consulta activamente el estado del escáner
- **Lock:** Mecanismo para prevenir acceso simultáneo a un recurso

---

## 14. Referencias

- [README.md](./README.md) - Documentación de usuario y desarrollo
- [context.txt](./context.txt) - Documentación técnica detallada
- [TWAIN Specification](https://www.twain.org/) - Estándar TWAIN
- [Flask Documentation](https://flask.palletsprojects.com/) - Framework web
- [Toshiba e-Studio 2822AM Manual](https://toshibasa.co.za/) - Manual del escáner

---

## 15. Historial de Versiones

| Versión | Fecha | Autor | Cambios |
|---------|-------|-------|---------|
| 1.0 | Diciembre 2025 | Equipo POLIHC | PRD inicial - Fase 1 completada |

---

**Documento generado:** Diciembre 2025  
**Última actualización:** Diciembre 2025  
**Estado:** ✅ Fase 1 Completada - 🔄 Fase 2 En Progreso (Integración Django completada, pendiente pruebas y almacenamiento de los documentos)

