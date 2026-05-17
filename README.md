# Scanner Connector API (Flask)

Este proyecto es un **conector intermedio** entre un **escáner físico (Toshiba e-Studio 2822AM)** y una **aplicación web en Django**.

## 🎯 Objetivo

Proporcionar una API REST que permite:

- ✅ **Comunicación directa con el escáner** vía protocolo TWAIN
- ✅ **Endpoints HTTP** para control completo del proceso de escaneo
- ✅ **Gestión de sesiones** con bloqueo para prevenir escaneos simultáneos
- ✅ **Verificación de disponibilidad** del escáner con timeouts configurables
- ✅ **Detección inteligente** de hojas en ADF (bandeja) y flatbed (cristal)
- ✅ **Limpieza automática** de sesiones residuales
- ✅ **Entrega de imágenes WEBP (por defecto) o PNG (legacy)** listas para consumir desde Django

---

## 🔧 Stack Tecnológico

| Componente | Tecnología | Notas |
|------------|------------|-------|
| **Backend API** | Flask (Python) | Framework web ligero |
| **Python Version** | 3.13.7 (32 bits) | OBLIGATORIO para TWAIN |
| **Driver Escáner** | TWAIN 32 bits | Toshiba Scan Driver |
| **Sistema Operativo** | Windows 10/11 | 64 bits con Python 32 bits |
| **Formato Imágenes** | WEBP (por defecto) / PNG (legacy) | Compresión configurable |
| **Resoluciones** | 300 / 400 / 600 DPI | Configurable por petición |
| **Modos de Color** | Text / Gray / Color / Text+Photo | |
| **Funciones** | Dúplex, Rotación, Detección de blanco | |

---

## 📂 Estructura del Proyecto

```
scanner_connector_polihc_basic/
│
├── app.py                        # Servidor Flask principal (punto de entrada)
├── run_production.py             # Script de producción (Waitress)
├── run_with_console.py           # Script de producción con ventana
├── requirements.txt              # Dependencias Python
├── pytest.ini                    # Configuración de tests
├── context.txt                   # Documentación técnica
├── README.md                     # Este archivo
├── PRD.md                        # Documentación de producción
├── AUDITORIA_SEGURIDAD.md        # Auditoría de seguridad
├── usb_transfer_guide.md         # Guía de transferencia USB
│
├── config/                       # Configuración
│   ├── __init__.py
│   ├── config.py
│   └── settings.py
│
├── controllers/                  # Controladores de endpoints
│   ├── __init__.py
│   └── scan_controller.py
│
├── services/                     # Servicios y lógica TWAIN
│   ├── __init__.py
│   └── twain_connector.py
│
├── utils/                        # Utilidades generales
│   ├── __init__.py
│   ├── file_manager.py
│   ├── session_lock.py
│   └── list_scanners.py
│   # ...otros utilitarios
│
├── test/                         # Pruebas unitarias y de integración
│   ├── conftest.py
│   ├── test_concurrency.py
│   ├── test_file_manager.py
│   ├── test_integration.py
│   ├── test_scan_controller.py
│   ├── test_session_lock.py
│   └── t.txt
│
├── scripts/                      # Scripts auxiliares y de mantenimiento
│   ├── limpiar_logs.py           # Limpieza automática de logs (Python)
│   ├── security_audit.py         # Auditoría de seguridad
│   ├── security_audit_auto.py    # Auditoría automática
│   # ...otros scripts
│
├── logs/                         # Carpeta de logs (creada en runtime, gitignored)
│   └── api_production.log        # Log principal de la API
│   # ...otros logs
│
├── scans/                        # Carpeta temporal de imágenes escaneadas (gitignored)
│   └── session_*/                # Carpetas por sesión
│
├── instalar_tarea.ps1                    # Instala tarea programada (sin ventana)
├── instalar_tarea_con_ventana.ps1        # Instala tarea programada (con ventana)
├── iniciar_servidor.ps1                  # Script para iniciar servidor con acceso directo
├── instalar_tarea_auditoria.ps1          # Instala auditoría de seguridad
├── instalar_tarea_limpiar_logs.ps1       # Instala limpieza automática de logs
├── prepare_usb_transfer.ps1              # Prepara estructura para USB 
│
└── testsprite_tests/             # Documentos y pruebas externas
  ├── run_existing_tests.py
  ├── run_tests.py
  └── ...
```

---

## 🚀 Instalación y Ejecución

### 1️⃣ Requisitos Previos

- ✅ **Python 3.13.7 (32 bits)** instalado
- ✅ **Driver TWAIN** del escáner Toshiba instalado
- ✅ **Git** instalado
- ✅ **Tesseract OCR** instalado (opcional, para auto-rotación)
- ✅ **Escáner conectado** y encendido
- ✅ **Windows 10/11** (64 bits)

### 2️⃣ Configuración del Entorno

```bash
# Clonar el repositorio
git clone https://github.com/CamiloAndresV/scanner_connector_polihc_basic.git
cd scanner_connector_polihc_basic

# Crear entorno virtual (con Python 32 bits)
python -m venv venv

# Activar entorno virtual
venv\Scripts\activate

# Instalar dependencias
pip install -r requirements.txt
```

### 3️⃣ Ejecutar el Servidor

```bash
# DESARROLLO (con Swagger habilitado en /apidocs/)
python app.py

# PRODUCCIÓN (sin ventana, logs a archivo)
python run_production.py

# PRODUCCIÓN como Tarea Programada (ver sección Despliegue)
# pythonw.exe run_production.py
```

El servidor estará disponible en:
- 🌐 **Local**: `http://127.0.0.1:5000`
- 🔒 **Modo local únicamente**: sin Tailscale, sin VPS y sin exposición a red.

---

## 🔐 Producción con Django + JWT

### Variables de entorno obligatorias

```env
FLASK_SHARED_SECRET=valor-igual-al-de-django
FLASK_REQUIRE_AUTH=true
FLASK_JWT_ISSUER=django-polihc
```

Notas importantes:

- Si `FLASK_REQUIRE_AUTH=true` y falta `FLASK_SHARED_SECRET`, el conector detiene el arranque con error claro.
- Todos los endpoints `/api/scan/*` exigen `Authorization: Bearer <token>` cuando la auth está activa.
- El token debe ser JWT `HS256`, incluir `iss=django-polihc` y no estar vencido (`exp`).

Endpoints protegidos relevantes:

- `/api/scan/check-scanner`
- `/api/scan/start`
- `/api/scan/continue`
- `/api/scan/status`
- `/api/scan/finish`
- `/api/scan/cancel`
- `/api/scan/download/<session_id>/<filename>`
- `/api/scan/delete-page/<session_id>/<filename>`

---

## 📡 API Endpoints

### 🔍 **Verificación y Estado**

| Método | Ruta | Descripción | Códigos de Respuesta |
|--------|------|-------------|---------------------|
| `GET` | `/` | Estado del servicio | `200` |
| `GET` | `/api/scan/check-scanner` | Verifica disponibilidad del escáner | `200`, `503`, `504` |
| `GET` | `/api/scan/check-feeder` | Verifica si hay papel en ADF | `200`, `504` |
| `GET` | `/api/scan/status` | Estado del escaneo actual | `200` |

**Ejemplo `/check-scanner` con JWT:**
```bash
curl -X GET http://localhost:5000/api/scan/check-scanner \
  -H "Authorization: Bearer <JWT_VALIDO_DESDE_DJANGO>"
```

**Sin token (esperado 401):**
```bash
curl -i http://localhost:5000/api/scan/check-scanner
```

**Token inválido (esperado 401):**
```bash
curl -i -X GET http://localhost:5000/api/scan/check-scanner \
  -H "Authorization: Bearer token-invalido"
```

**Respuesta exitosa (200):**
```json
{
  "success": true,
  "message": "Escáner conectado y listo",
  "feeder": {"success": true, "message": "✅ Hay papel en el alimentador."},
  "flatbed": {"success": false, "message": "⚠ No hay hoja en el cristal."}
}
```

**Respuesta timeout (504):**
```json
{
  "success": false,
  "message": "No se pudo conectar con el escáner. Verifique que esté encendido y conectado.",
  "feeder": {"success": false, "timeout": true, "message": "Timeout..."},
  "flatbed": {"success": false, "timeout": true, "message": "Timeout..."}
}
```

---

### 🖨️ **Gestión de Escaneo**

| Método | Ruta | Descripción | Parámetros |
|--------|------|-------------|-----------|
| `POST` | `/api/scan/start` | Inicia nueva sesión de escaneo | `user_id`, `dpi`, `color_mode`, `feeder`, etc. |
| `POST` | `/api/scan/continue` | Continúa escaneando en sesión activa | Mismos parámetros que start más `session_id` |
| `POST` | `/api/scan/cancel` | Cancela escaneo y elimina archivos | - |
| `POST` | `/api/scan/finish` | Finaliza sesión y limpia archivos | - |

**Ejemplo `/start`:**
```bash
curl -X POST http://localhost:5000/api/scan/start \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "usuario123",
    "dpi": 300,
    "color_mode": "Color",
    "duplex": false,
    "feeder": true,
    "page_size": "A4-R",
    "rotation": "off"
  }'
```

**Respuesta:**
```json
{
  "success": true,
  "session_id": "session_1730739456_usuario123",
  "message": "Escaneo iniciado correctamente",
  "scan_params": { ... }
}
```

---

### 📄 **Recuperación de Imágenes**

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET` | `/api/scan/pages` | Lista páginas de sesión activa |
| `GET` | `/api/scan/pages/<session_id>` | Lista páginas de sesión específica |
| `GET` | `/api/scan/download/<session_id>/<filename>` | Descarga imagen WEBP/PNG |

**Ejemplo recuperación desde Django:**
```python
# 1. Obtener lista de páginas
response = requests.get(f'http://localhost:5000/api/scan/pages/{session_id}')
pages = response.json()['pages']

# 2. Descargar cada imagen
for page in pages:
    filename = page['filename']
    url = f'http://localhost:5000/api/scan/download/{session_id}/{filename}'
    img_data = requests.get(url).content
    
    # Guardar en Django
    with open(f'media/scans/{filename}', 'wb') as f:
        f.write(img_data)
```

---

### 🧹 **Limpieza**

| Método | Ruta | Descripción |
|--------|------|-------------|
| `POST` | `/api/scan/run-cleanup` | Limpieza manual de sesiones residuales |
| `DELETE` | `/api/scan/cleanup/<session_id>` | Elimina archivos de sesión específica |

**Limpieza automática programada**: 
- Se ejecuta diariamente a las **15:30** (configurable en `app.py`)
- Elimina sesiones con más de **20 minutos** de inactividad

---

## ⚙️ Configuración Avanzada

### 🕐 **Timeouts**

Los timeouts están configurados para prevenir bloqueos cuando el escáner está apagado o desconectado:

```python
# En config/config.py

# Timeout para verificación de alimentador (ADF)
FEEDER_TIMEOUT = 7  # segundos

# Timeouts bifásicos para cristal (flatbed)
FLATBED_CONNECTION_TIMEOUT = 12  # Fase 1: conexión al hardware (6-12s recomendado)
FLATBED_SCAN_TIMEOUT = 28        # Fase 2: escaneo activo (hasta 300s en producción)
```

### 🖼️ **Formato de imágenes (WEBP/PNG)**

El formato es configurable por variable de entorno (WEBP por defecto, PNG legacy):

```env
SCAN_IMAGE_FORMAT=webp
SCAN_IMAGE_QUALITY=85
SCAN_IMAGE_METHOD=4
SCAN_IMAGE_LOSSLESS=False
```

Si se usa PNG, los parámetros de calidad y método no aplican.

### 📋 **Parámetros de Escaneo**

```python
# config/config.py

DEFAULT_DPI = 300                    # Resolución por defecto
ALLOWED_DPI = [300, 400, 600]        # Resoluciones permitidas

DEFAULT_COLOR_MODE = "Color"         # Modo de color por defecto
SCAN_MODES = ["Text", "Gray", "Color", "Text/Photo"]

DEFAULT_PAGE_SIZE = "LT-R"           # Tamaño de página por defecto
PAGE_SIZES = {
    "LT-R": "Letter",
    "A4-R": "A4 Portrait",
    "13-LG": "Legal 13",
    "A5-R": "A5 portrait",
}

ROTATIONS = ["off", "right90", "180", "left90"]
```

---

## 🔒 Sistema de Bloqueo de Sesiones

El proyecto implementa un **sistema de sesiones exclusivas** para prevenir conflictos:

- ✅ Solo **un usuario** puede escanear a la vez
- ✅ Sesiones tienen **timeout de 20 minutos**
- ✅ **Bloqueo automático** al iniciar escaneo
- ✅ **Liberación automática** al finalizar o cancelar
- ✅ **Limpieza programada** de sesiones expiradas

```python
# Intentar adquirir bloqueo
lock_result = session_manager.acquire_lock(user_id)  # Default: 20 minutos

if not lock_result['success']:
    # Escáner ocupado por otro usuario
    return jsonify({'error': 'Escáner en uso'}), 409

# ... realizar escaneo ...

# Liberar bloqueo
session_manager.release_lock(session_id)
```

---

## 🐛 Solución de Problemas

### ❌ Error: "No se pudo inicializar TWAIN"

**Causa**: Python no es de 32 bits o driver TWAIN no instalado.

**Solución**:
```bash
# Verificar versión de Python
python --version
# Debe mostrar: Python 3.13.7 (32-bit)

# Reinstalar driver TWAIN del escáner
# Descargar de: https://toshibasa.co.za/download-printer-drivers/
```

---

### ❌ Endpoint `/check-scanner` se queda cargando

**Causa**: Escáner apagado/desconectado y TWAIN bloqueado.

**Solución**: Ya implementado con timeouts. El endpoint responde en máximo **28 segundos** con error 504.  Si sigue sin funcionar, cierra el servidor y 
revsa en Scan Editor si hay conexion.

---

### ❌ "Sesión no encontrada" al descargar imágenes

**Causa**: Carpeta de sesión fue eliminada por limpieza automática.

**Solución**: 
- Aumentar timeout de inactividad en `perform_cleanup()` (línea 171)
- Descargar imágenes inmediatamente después de escanear

---

## 🔗 Integración con Django

### Flujo Recomendado (Pull Strategy)

```python
# views.py en Django
import requests
import time

def escanear_documento(request):
    # 1. Iniciar escaneo
    response = requests.post('http://localhost:5000/api/scan/start', json={
        'user_id': request.user.id,
        'feeder': True,
        'dpi': 300,
        'color_mode': 'Color'
    })
    
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
    pages_response = requests.get(f'http://localhost:5000/api/scan/pages/{session_id}')
    pages = pages_response.json()['pages']
    
    # 4. Descargar cada imagen
    for page in pages:
        filename = page['filename']
        img_url = f'http://localhost:5000/api/scan/download/{session_id}/{filename}'
        img_data = requests.get(img_url).content
        
        # Guardar en Django
        with open(f'media/scans/{filename}', 'wb') as f:
            f.write(img_data)
    
    # 5. Limpiar Flask
    requests.delete(f'http://localhost:5000/api/scan/cleanup/{session_id}')
    
    return JsonResponse({'success': True, 'imagenes': len(pages)})
```

---

## 📌 Notas Importantes

### ⚠️ Limitaciones

- **Python 32 bits obligatorio**: TWAIN solo funciona en arquitectura de 32 bits
- **Windows únicamente**: TWAIN no está disponible en Linux/macOS
- **Un escáner a la vez**: El sistema está diseñado para un solo dispositivo físico
- **Formato configurable (WEBP por defecto, PNG legacy)**: No se generan PDFs en este servicio

### 🔮 Desarrollo Futuro

- La **generación de PDF/A** se realizará en Django después de que el usuario reordene/edite las imágenes
- El conector solo entrega **imágenes WEBP (por defecto) o PNG (legacy)**
- Si el usuario cancela, las imágenes temporales se eliminan automáticamente

---

## 📋 Checklist de Tareas Completadas

- [x] ✅ Implementación de endpoints RESTful completos
- [x] ✅ Sistema de sesiones con bloqueo exclusivo
- [x] ✅ Verificación de disponibilidad del escáner con timeouts
- [x] ✅ Detección de hojas en ADF y flatbed
- [x] ✅ Limpieza automática programada de sesiones
- [x] ✅ Manejo robusto de errores y timeouts
- [x] ✅ Soporte para modo ADF y flatbed
- [x] ✅ Detección de páginas en blanco
- [x] ✅ Rotación de imágenes
- [x] ✅ Escaneo dúplex
- [x] ✅ Múltiples resoluciones y modos de color
- [x] ✅ Documentación completa

### 🐛 Correcciones Recientes (Diciembre 2025 - Enero 2026)

- [x] ✅ **WinError 32 resuelto**: Implementado context manager PIL en `twain_connector.py` y `image_orientation.py`
- [x] ✅ **Memory leaks eliminados**: Cierre explícito de imágenes con `img.close()` y `gc.collect()`
- [x] ✅ **Timeouts estandarizados**: 20 minutos para sesiones, 7s ADF, 28s Flatbed
- [x] ✅ **Logging mejorado**: Todos los `print()` reemplazados por `logger.*`
- [x] ✅ **Shutdown limpio**: Eliminados logs duplicados al cerrar servidor

### ✅ Mejoras de Producción (Enero 2026)

- [x] ✅ **Despliegue con Tarea Programada**: Compatible con driver TWAIN y ejecución interactiva
- [x] ✅ **Dos modos de instalación**: Sin ventana (silencioso) o con ventana de logs protegida
- [x] ✅ **Ventana con logs coloridos**: Muestra logs en tiempo real con `colorama` (modo ventana)
- [x] ✅ **Protección de ventana**: Botón X deshabilitado en modo consola; se puede detener con Ctrl+C o Stop-ScheduledTask
- [x] ✅ **Logging rotativo**: Archivos de log con rotación automática (máx 30MB total)
- [x] ✅ **Auto-reinicio**: Configurado para reiniciar hasta 5 veces si falla
- [x] ✅ **Scripts de instalación portables**: Detectan rutas automáticamente
- [x] ✅ **Limpieza automática de logs**: Tarea programada cada martes 10:00 AM
  - Elimina logs operativos (*.log) semanalmente
  - Conserva el reporte mensual `cleanup_audit.txt`
  - Genera `resumen_limpieza_*.log` por ejecución
- [x] ✅ **Auditoría de seguridad automática**: Cada martes 9:00 AM
  - Detecta vulnerabilidades con pip-audit
  - Reporta hallazgos sin actualizar dependencias automáticamente
  - Consolida resultados en `logs/cleanup_audit.txt` (retención mensual)
- [x] ✅ **Acceso directo para inicio rápido**: Script `iniciar_servidor.ps1`
  - Simplifica inicio del servidor desde escritorio
  - No reinstala la tarea (solo inicia)
  - Verifica estado antes de iniciar
  - Documentación completa en `usb_transfer_guide.md`

### 🔄 Pendiente

- [ ] Ponerlo en produccion real y monitorear rendimiento
- [ ] Ajustar el inicio y cierre de servidor para facilitar su uso

---

## 📄 Licencia

Este proyecto es de uso interno para la organización.

---

## 📞 Soporte

Para problemas técnicos o consultas:
- **Repositorio**: https://github.com/CamiloAndresV/scanner_connector_polihc_basic
- **Branch actual**: `service/backend`
---

**Última actualización**: Marzo 30, 2026

# Tests - Solo para desarrollo

Esta carpeta contiene tests unitarios y de integración.
**NO se ejecutan en producción.**

## Uso (solo desarrollo):
```bash
pytest test/



---
🏥 Health Check Endpoint - Importancia para Producción
¿Qué es y para qué sirve?
El endpoint /api/scan/health permite que sistemas externos verifiquen si tu API está funcionando correctamente.

Usos principales:

Caso de Uso	Quién lo usa	Para qué
Monitoreo	Nagios, Zabbix, Prometheus	Alertas si el servicio cae
Load Balancer	Nginx, HAProxy	Saber si puede enviar requests
Kubernetes/Docker	Orquestador	Reiniciar containers fallidos
Django	Tu app frontend	Verificar si puede escanear
Ejemplo de uso:
curl http://localhost:5000/api/scan/health

Respuesta esperada:
{
  "status": "healthy",
  "timestamp": "2026-01-08T10:30:00",
  "version": "1.0.0"
}

✅ Recomendación
SÍ, mantenerlo y usarlo cuando configures el servicio Windows. Es estándar en cualquier API de producción.

🚀 Servidor de Producción - Flask vs Waitress
⚠️ El Problema Actual
app.run(debug=is_development, ...)  # Servidor de desarrollo Flask
El servidor de desarrollo de Flask:

❌ NO es seguro para producción
❌ NO maneja múltiples requests eficientemente
❌ NO tiene workers para paralelismo
❌ Se reinicia solo cuando detecta cambios (modo debug)
🎯 Opciones para Windows
Opción	Pros	Contras	Recomendado
Waitress	Nativo Windows, fácil, estable	Menos features que Gunicorn	✅ SÍ
Gunicorn	Potente, muchas opciones	❌ No funciona en Windows	❌ NO
Hypercorn	Async, moderno	Más complejo	⚠️ Opcional
Flask dev	Ya lo tienes	❌ Inseguro en producción	❌ NO
✅ Recomendación: Waitress + Tarea Programada de Windows
Waitress es la mejor opción para tu proyecto porque:

✅ Nativo Windows - Sin dependencias de Unix
✅ Estable y probado - Usado en producción por miles de proyectos
✅ Compatible con TWAIN - No interfiere con el driver de 32 bits
✅ Fácil de configurar - Un solo comando
✅ Thread-safe - Maneja múltiples requests correctamente
🔧 Implementación Paso a Paso
Paso 1: Instalar Waitress
# Con venv activado
pip install waitress
pip freeze > requirements.txt

Paso 2: Crear Script de Inicio
Crea un archivo run_production.py:


Paso 3: Probar Manualmente
# Probar que funciona
python run_production.py

# En otra terminal, verificar health
curl http://localhost:5000/api/scan/health

----
## 🪟 Despliegue en Producción (Tarea Programada de Windows)

> **Nota**: Se usa Tarea Programada en lugar de Servicio Windows porque el driver TWAIN
> requiere una sesión de usuario interactiva (Session 0 isolation).

### 📌 Dos Opciones de Instalación

Elige según tus necesidades:

| Opción | Script | Descripción | Uso Recomendado |
|--------|--------|-------------|-----------------|
| **A - Sin Ventana** | `instalar_tarea.ps1` | Ejecución silenciosa en segundo plano con `pythonw.exe` | Producción estable, servidores sin monitor |
| **B - Con Ventana** | `instalar_tarea_con_ventana.ps1` | Ventana visible con logs en tiempo real (coloridos) | Monitoreo activo, debugging, desarrollo |

### Opción A: Instalación Sin Ventana (Silencioso)

**Ventajas:**
- ✅ No interfiere con otras aplicaciones
- ✅ Ideal para servidores sin monitor
- ✅ Logs solo en archivo (`logs/api_production.log`)

**Instalación:**

En PowerShell como **Administrador**:

```powershell
cd C:\ruta\al\proyecto\scanner_connector_polihc_basic
.\instalar_tarea.ps1
```

### Opción B: Instalación Con Ventana Protegida

**Ventajas:**
- ✅ Logs en tiempo real con colores (verde=INFO, amarillo=WARNING, rojo=ERROR)
- ✅ Ventana **no se puede cerrar** accidentalmente (botón X deshabilitado)
- ✅ Permite Ctrl+C para cierre controlado
- ✅ Útil para monitoreo visual del escáner

**Instalación:**

En PowerShell como **Administrador**:

```powershell
cd C:\ruta\al\proyecto\scanner_connector_polihc_basic
.\instalar_tarea_con_ventana.ps1
```

**⚠️ Importante:** La ventana se puede cerrar con Ctrl+C o con:
```powershell
Stop-ScheduledTask -TaskName "tarea conector con ventana"
```

### 🧹 Limpieza Automática de Sesiones

**Configuración:**
- **Scheduler diario**: 3:30 PM
- **Timeout de sesión**: 20 minutos de inactividad
- **Criterio de eliminación**: Carpetas con más de 20 minutos sin modificación

**⚠️ Buenas Prácticas:**

1. **Siempre finalice el escaneo**: Use el endpoint `/api/scan/finish` o el botón "Finalizar" en Django
2. **No cierre el navegador abruptamente**: Esto puede dejar sesiones huérfanas
3. **Si olvida finalizar**: Las carpetas se limpiarán automáticamente después de 20 minutos
4. **Limpieza manual**: Si necesita limpiar inmediatamente, use:
   ```bash
   curl -X POST http://localhost:5000/api/scan/run-cleanup
   ```

**Protección de sesiones activas:**
- Las sesiones en progreso (`is_scanning=True`) NO se eliminan
- Solo se borran carpetas inactivas por más de 20 minutos

### Paso 2: Verificar Funcionamiento

Verificar que la tarea está registrada:

```powershell
Get-ScheduledTask -TaskName "Scanner Connector API*"
```

### Características de las Tareas Programadas

**Configuración Común:**

| Característica | Configuración |
|----------------|---------------|
| **Trigger** | Al iniciar sesión del usuario |
| **Reintentos** | 5 intentos, 1 minuto entre cada uno |
| **Límite tiempo** | Sin límite (corre indefinidamente) |
| **Prioridad** | Alta (4) |
| **Logs** | `logs/api_production.log` con rotación automática |

**Diferencias entre modos:**

| Aspecto | Sin Ventana (`instalar_tarea.ps1`) | Con Ventana (`instalar_tarea_con_ventana.ps1`) |
|---------|-----------------------------------|------------------------------------------------|
| **Trigger** | ✅ Al iniciar sesión del usuario | ❌ Inicio manual (sin trigger en el script actual) |
| **Ejecutable** | `pythonw.exe` | `python.exe` |
| **Script** | `run_production.py` | `run_with_console.py` |
| **Logs en pantalla** | ❌ No | ✅ Sí, con colores |
| **Protección ventana** | N/A | ✅ Botón X deshabilitado (Ctrl+C habilitado) |
| **Uso recomendado** | Producción estable | Monitoreo/debugging

---

### 🖱️ Acceso Directo para Iniciar Servidor (Opcional)

**Prerequisito:** Haber ejecutado `instalar_tarea_con_ventana.ps1` al menos una vez.

**¿Para qué sirve?**
- Simplifica el inicio del servidor (doble clic vs abrir PowerShell)
- No necesitas recordar comandos
- No reinstala la tarea cada vez (solo la inicia)
- Ideal para usuarios no técnicos

**Crear acceso directo manualmente:**

1. Clic derecho en el Escritorio → Nuevo → Acceso directo
2. En "Ubicación", pega:
   ```
   C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe -ExecutionPolicy Bypass -File "C:\ruta\al\proyecto\scanner_connector_polihc_basic\iniciar_servidor.ps1"
   ```
3. Nombre: `🚀 Iniciar Scanner Server`
4. Clic derecho en el acceso → Propiedades → Avanzadas → ✅ Marcar "Ejecutar como administrador"

**Uso:**
- Doble clic en el acceso directo
- Confirmar permisos UAC
- El script verifica si la tarea existe y si el servidor ya está corriendo
- Inicia el servidor si no está activo
- Para detener: Ctrl+C en la ventana o `Stop-ScheduledTask -TaskName "tarea conector con ventana"`

**Ver:** [usb_transfer_guide.md](usb_transfer_guide.md) para instrucciones completas.

---

Get-Process pythonw

# Probar endpoint
(Invoke-WebRequest -Uri "http://localhost:5000/api/scan/health" -UseBasicParsing).Content

# Probar escáner
(Invoke-WebRequest -Uri "http://localhost:5000/api/scan/check-scanner" -UseBasicParsing).Content
```

### 📋 Comandos de Control

```powershell
# Ver estado de la tarea
Get-ScheduledTask -TaskName "Scanner Connector API" | Select-Object State

# Iniciar manualmente
Start-ScheduledTask -TaskName "Scanner Connector API"

# Detener
Stop-ScheduledTask -TaskName "Scanner Connector API"

# Ver últimas líneas del log
Get-Content "logs\api_production.log" -Tail 50

# Ver información de última ejecución
Get-ScheduledTaskInfo -TaskName "Scanner Connector API"
```

### Características de la Tarea Programada

| Característica | Configuración |
|----------------|---------------|
| **Ejecutable** | `pythonw.exe` (sin ventana) |
| **Trigger** | Al iniciar sesión del usuario |
| **Reintentos** | 5 intentos, 1 minuto entre cada uno |
| **Límite tiempo** | Sin límite (corre indefinidamente) |
| **Prioridad** | Alta (4) |
| **Logs** | `logs/api_production.log` con rotación automática |


🏥 Monitoreo del Health Check
Script de Monitoreo (Opcional)
Crea scripts/monitor_health.py:
"""
Script para monitorear el health check del servicio.
Puede ejecutarse como tarea programada de Windows.
"""
import requests
import sys
from datetime import datetime

def check_health():
    try:
        response = requests.get('http://localhost:5000/api/scan/health', timeout=5)
        if response.status_code == 200:
            print(f"[{datetime.now()}] ✅ Servicio saludable")
            return 0
        else:
            print(f"[{datetime.now()}] ⚠️ Respuesta inesperada: {response.status_code}")
            return 1
    except requests.exceptions.ConnectionError:
        print(f"[{datetime.now()}] ❌ Servicio no responde - posiblemente caído")
        return 2
    except requests.exceptions.Timeout:
        print(f"[{datetime.now()}] ❌ Timeout - servicio lento o bloqueado")
        return 3

if __name__ == "__main__":
    sys.exit(check_health())
```

**Tarea Programada Windows**:
```powershell
# Crear tarea que ejecute cada 5 minutos
schtasks /create /tn "ScannerConnector_HealthCheck" /tr "C:\Users\ospin\Clonaciones\scanner_connector_polihc_basic\venv\Scripts\python.exe C:\Users\ospin\Clonaciones\scanner_connector_polihc_basic\scripts\monitor_health.py" /sc minute /mo 5
```

---

## 🔒 Auditoría de Seguridad Automática

Sistema que **audita vulnerabilidades cada martes a las 9:00 AM** y **reporta hallazgos** sin actualizar dependencias automáticamente.

### 🚀 Instalación Rápida

```powershell
# 1. Instalar pip-audit
pip install pip-audit

# 2. Instalar tarea programada (como Administrador)
.\instalar_tarea_auditoria.ps1
```

**Listo.** Ver instrucciones completas en **[AUDITORIA_SEGURIDAD.md](AUDITORIA_SEGURIDAD.md)**

---

## 📊 Resumen Final
Componente	Estado	Notas
Health Check	✅ Ya implementado	/api/scan/health
Waitress	📦 Por instalar	pip install waitress
run_production.py	📄 Por crear	Script de inicio
Tarea Programada	✅ Implementada	Compatible con TWAIN
Monitoreo	🔍 Opcional	Script + tarea programada
🎯 Orden de Implementación
✅ pip install waitress
✅ Crear run_production.py
✅ Probar manualmente: python run_production.py
✅ Verificar health: curl http://localhost:5000/api/scan/health
✅ Instalar tarea programada de Windows
✅ Verificar reinicio automático de la tarea
✅ Probar reinicio automático