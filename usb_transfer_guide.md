# 📦 Guía de Transferencia USB - Scanner Connector API

## ✅ Checklist Pre-Transferencia

Antes de copiar a USB, verifica que estos archivos/carpetas existan:

### **Archivos Esenciales** ✅
- [x] [app.py](./app.py) - Servidor Flask principal
- [x] [run_production.py](./run_production.py) - Script de producción con Waitress
- [x] [requirements.txt](./requirements.txt) - Dependencias Python
- [x] [.env.example](./.env.example) - Plantilla de configuración
- [x] [.env](./.env) - Configuración actual (contiene secretos, proteger USB)
- [x] [README.md](./README.md) - Documentación completa
- [x] [pytest.ini](./pytest.ini) - Configuración de tests

### **Scripts de Instalación** ✅
- [x] [instalar_tarea.ps1](./instalar_tarea.ps1) - Instalador de Tarea Programada sin ventana
- [x] [instalar_tarea_con_ventana.ps1](./instalar_tarea_con_ventana.ps1) - Instalador de tarea programada con ventana
- [x] [iniciar_servidor.ps1](./iniciar_servidor.ps1) - Script para iniciar servidor con acceso directo
- [x] [instalar_tarea_auditoria.ps1](./instalar_tarea_auditoria.ps1) - Auditoría de seguridad
- [x] [instalar_tarea_limpiar_logs.ps1](./instalar_tarea_limpiar_logs.ps1) - Limpieza de logs

### **Carpetas del Proyecto** ✅
- [x] `config/` - Configuración (settings.py, config.py)
- [x] `controllers/` - Endpoints (scan_controller.py)
- [x] `services/` - Lógica TWAIN (twain_connector.py)
- [x] `utils/` - Utilidades (file_manager.py, session_lock.py, etc.)
- [x] `test/` - Tests unitarios
- [x] `scripts/` - Scripts de auditoría y limpieza (Python)
- [x] `.github/` - Configuración de GitHub Actions

### **Carpetas a EXCLUIR** ❌
- [ ] `venv/` - Entorno virtual (se recrea en PC destino)
- [ ] `__pycache__/` - Archivos compilados
- [ ] `.pytest_cache/` - Caché de tests
- [ ] `scans/` - Archivos temporales de escaneo
- [ ] `logs/` - Logs antiguos
- [ ] `.git/` - Historial de Git (opcional, solo si no usas Git en destino)

---

## 📋 Paso 1: Preparar USB

### Crear estructura en USB

```
USB:\scanner_connector_polihc_basic\
├── app.py
├── run_production.py
├── run_with_console.py
├── requirements.txt
├── .env
├── .env.example
├── .gitignore
├── README.md
├── PRD.md
├── usb_transfer_guide.md
├── AUDITORIA_SEGURIDAD.md
├── context.txt
├── pytest.ini
├── instalar_tarea.ps1
├── instalar_tarea_con_ventana.ps1
├── iniciar_servidor.ps1
├── instalar_tarea_auditoria.ps1
├── instalar_tarea_limpiar_logs.ps1
├── prepare_usb_transfer.ps1
├── config\
├── controllers\
├── services\
├── utils\
├── test\
├── .github\
└── scripts\
```

### Copiar a USB (PowerShell)

#### Opcion 1: prepare_usb_transfer.ps1 (recomendado)

> Cambia la letra del USB segun corresponda (E, D, etc.).

```powershell
.\prepare_usb_transfer.ps1 -DestinoUSB "D:\scanner_connector_polihc_basic"
```

#### Opcion 2: copia manual

```powershell
# En el PC actual, en caso de no ser busca la ruta que contiene el proyecto
cd C:\Users\ospin\Clonaciones\scanner_connector_polihc_basic

# Reemplaza E: con la letra real del USB (E, D, etc.)
$destino = "E:\scanner_connector_polihc_basic"
New-Item -ItemType Directory -Path $destino -Force

# Copiar archivos esenciales
Copy-Item -Path app.py, run_production.py, run_with_console.py, requirements.txt, .env, .env.example, README.md, PRD.md, context.txt, pytest.ini, AUDITORIA_SEGURIDAD.md, usb_transfer_guide.md -Destination $destino
Copy-Item -Path instalar_tarea.ps1, instalar_tarea_con_ventana.ps1, iniciar_servidor.ps1, instalar_tarea_auditoria.ps1, instalar_tarea_limpiar_logs.ps1, prepare_usb_transfer.ps1 -Destination $destino

# Copiar carpetas (excluyendo venv, __pycache__, etc.)
$carpetas = @("config", "controllers", "services", "utils", "test", "scripts", ".github")
foreach ($carpeta in $carpetas) {
    Copy-Item -Path $carpeta -Destination $destino -Recurse -Force -Exclude "__pycache__", "*.pyc"
}

Write-Host "✅ Proyecto copiado a USB: $destino"
```

---

## 🖥️ Paso 2: Instalación en PC Nuevo
## Recuerda instalar todo antes de ejecutar scripts, para evitar problemas de PATH o dependencias faltantes. reinicia el equipo si es necesario.

### **Requisitos Previos**

| Componente | Versión | Descarga |
|------------|---------|----------|
| **Python** | 3.13.7 (32 bits) | [python.org](https://www.python.org/downloads/release/python-3137/) |
| **Driver TWAIN** | Toshiba e-Studio 2822AM + Scan Editor | [Toshiba Drivers](https://toshibasa.co.za/download-printer-drivers/) |
| **Driver TWAIN SAVIN** | Savin (impresora) | [Savin Drivers](https://support.ricoh.com/bb/html/dr_ut_e/rc2/model/mp301/mp301.htm?lang=es) |
| **Tesseract OCR** | 5.3.20221222 | [docs.coro.net](https://docs.coro.net/featured/agent/install-tesseract-windows) o tambien [digi.bib](https://digi.bib.uni-mannheim.de/tesseract/) |
| **Windows** | 10/11 (64 bits) | - |

### **2.1 Instalar Python 32 bits**

> ⚠️ **CRÍTICO**: Debe ser Python **32 bits**, no 64 bits (TWAIN solo funciona en 32 bits)

1. Descargar: https://www.python.org/ftp/python/3.13.7/python-3.13.7.exe
2. **Ejecutar instalador**:
   - ✅ Marcar "Add Python 3.13 to PATH"
   - ✅ Seleccionar "Customize installation"
   - ✅ En "Advanced Options", marcar "Install for all users" (no necesario)
   - ✅ Cambiar ruta a `C:\Python313-32` (para identificar fácilmente) (no necesario)
3. Verificar instalación:
   ```powershell
   python --version
   # Debe mostrar: Python 3.13.7
   
   python -c "import struct; print(struct.calcsize('P') * 8)"
   # Debe mostrar: 32
   ```

### **2.2 Instalar Drivers TWAIN (Toshiba + Savin)**

1. Conectar escáner Toshiba e-Studio 2822AM
2. Descargar driver desde: https://toshibasa.co.za/download-printer-drivers/
3. Ejecutar instalador como Administrador
4. Reiniciar PC si es necesario
5. Verificar en "Dispositivos e impresoras" que aparezca la impresora o el escáner
6. Aparte del .exe del driver, tambien instalar la app de "Scan Editor" que viene en la misma carpeta del driver
7. Abrir Scan Editor y validar que el escáner responda (prueba de conexión)
8. Instalar el driver TWAIN de la impresora Savin (dejar configuración por defecto)

### **2.3 Instalar Tesseract OCR** (Opcional, para auto-rotación)

1. Documentación: https://github.com/tesseract-ocr/tesseract
2. Descargar: 1. https://digi.bib.uni-mannheim.de/tesseract/ - 2. https://docs.coro.net/featured/agent/install-tesseract-windows
3. Instalar en `C:\Program Files (x86)\Tesseract-OCR\`
4. En el instalador, seleccionar idioma Español (spa) si está disponible
5. Verificar idiomas instalados:
   ```powershell
   tesseract --list-langs
   # Debe listar: spa
   ```
6. Agregar a PATH:
   ```powershell
   # Como Administrador, si no funciona revisar si quedo en archivos del programa normal o el de (x86)
   [Environment]::SetEnvironmentVariable("Path", $env:Path + ";C:\Program Files (x86)\Tesseract-OCR", "Machine")
   ```
---

### **2.4 Instalar git**
1. Descargar git desde: https://git-scm.com/download/win
2. Ejecutar instalador con opciones por defecto
3. Verificar instalación:
   ```powershell
   git --version
   # Debe mostrar: git version X.Y.Z
   # Ejem: git version 2.52.0.windows.1
   ```
---

**Nota:** Por decisión de la empresa, el sistema opera solo en modo local. No se usa Tailscale, VPS ni acceso remoto.


## 📁 Paso 3: Configurar Proyecto

### **3.1 Copiar desde USB**

```powershell
# Copiar proyecto a ubicación permanente en el otro equipo
Copy-Item -Path "E:\scanner_connector_polihc_basic" -Destination "C:\Proyectos\" -Recurse

cd C:\Proyectos\scanner_connector_polihc_basic
```

### **3.2 Crear Entorno Virtual**

```powershell
# Crear venv con Python 32 bits
# si no funciona, puedes probar cerrando terminal y abriendo una nueva, revisa que si este en el path, lo ideal es instalar todo primero para luego crear el entorno virtual
python -m venv venv

# Activar venv
.\venv\Scripts\activate

# si no funciona por deshabilitación de scripts, ejecutar:
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process
Set-ExecutionPolicy RemoteSigned
Set-ExecutionPolicy Unrestricted # Para volver a bloquear
# si quieres cambiar al usuario usar CurrentUser o maquina completa, usar LocalMachine luego de -Scope:
# Luego activar nuevamente

# Verificar que es 32 bits
python -c "import struct; print(struct.calcsize('P') * 8)"
# Debe mostrar: 32
```

### **3.3 Instalar Dependencias**

```powershell
# Con venv activado
pip install --upgrade pip
pip install -r requirements.txt

# Verificar instalación crítica
python -c "import twain; print('✅ TWAIN OK')"
python -c "import flask; print('✅ Flask OK')"
python -c "import waitress; print('✅ Waitress OK')" # waitress es solo para producción para servir la app
```

### **3.4 Configurar Variables de Entorno**

```powershell
# Si ya viene .env desde el USB, solo valida y edita
Test-Path .env

# Si no existe, copiar plantilla
Copy-Item .env.example .env

# Editar .env con tus valores
notepad .env
```

> Asegurar que las variables de entorno se creen dentro de la carpeta del proyecto.

**Configuración mínima en `.env`:**

```ini
# OBLIGATORIO - Generar clave segura
SECRET_KEY=tu-clave-secreta-de-al-menos-25-caracteres-aqui

# Modo de ejecución
DEBUG=False

# Swagger (solo desarrollo)
SWAGGER_USER=admin
SWAGGER_PASSWORD=tu-contraseña-segura

# Django
DJANGO_URL=http://localhost:8000

# Escáner (verificar nombre exacto)
SCANNER_NAME=Type301 Scanner

# Nombre del escáner secundario para fallback automático (opcional)
SCANNER_NAME_SECONDARY=e-STUDIO2822ASeries Scan Driver


# Si es True, cuando el principal no esté disponible se probará el secundario
SCANNER_AUTO_FALLBACK=True


# Tesseract (ajustar si instalaste en otra ruta)
TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe

# Timeouts
FEEDER_TIMEOUT=7
FLATBED_CONNECTION_TIMEOUT=12
FLATBED_SCAN_TIMEOUT=28

# Logging
LOG_LEVEL=INFO
```

**Generar SECRET_KEY segura:**

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
# Copiar el resultado a .env
```

### **3.5 Verificar Nombre del Escáner**

```powershell
# Listar escáneres disponibles
python -c "from utils.list_scanners import list_available_scanners; print(list_available_scanners())"

# si no funciona prueba con:
python -c "import twain; sm = twain.SourceManager(0); print(sm.GetSourceList())"

# O ejecutar script directamente
python utils/list_scanners.py

# Copiar el nombre exacto a .env → SCANNER_NAME
```

---

## 🧪 Paso 4: Probar Instalación

### **4.1 Prueba Manual (Desarrollo)**

```powershell
# Con venv activado
python app.py

# En otra terminal, probar endpoints
curl http://localhost:5000/
curl http://localhost:5000/api/scan/health
curl http://localhost:5000/api/scan/check-scanner
```

**Respuestas esperadas:**

```json
// GET /
{
  "message": "Scanner Connector API",
  "status": "running",
  "version": "1.0"
}

// GET /api/scan/health
{
  "status": "healthy",
  "timestamp": "2026-01-14T16:00:00",
  "is_scanning": false
}

// GET /api/scan/check-scanner
{
  "success": true,
  "message": "Escáner conectado y listo",
  "hardware_connected": true,
  "adf_status": "ready"
}
```

### **4.2 Prueba con Waitress (Producción)**

```powershell
# Detener app.py si está corriendo (Ctrl+C)

# Ejecutar con Waitress
python run_production.py

# Verificar logs
Get-Content logs\api_production.log -Tail 20
```

### **4.3 Ejecutar Tests** (Opcional)

```powershell
# Con venv activado
pytest test/ -v

# Tests de concurrencia
pytest test/test_concurrency.py -v

# Con cobertura
pytest test/ --cov=. --cov-report=html
```

---

## 🚀 Paso 5: Despliegue en Producción

### **Opción A: Tarea Programada de Windows** (Recomendado)

> ✅ **Ventaja**: Compatible con TWAIN (requiere sesión de usuario)

```powershell
# Como Administrador
cd C:\Proyectos\scanner_connector_polihc_basic
.\instalar_tarea.ps1

# Si quieres ver ventana de consola, recuerda verificar que la ruta si sea correcta, sino ir mejor directamente a la carpeta del proyecto, ya que esta es una ruta por defecto:
cd C:\Proyectos\scanner_connector_polihc_basic
.\instalar_tarea_con_ventana.ps1

# si los comandos no funcionan, verifica que si estes en modo administrador y que los .ps1 esten en codificación UTF-8 With BOM para evitar errores de ejecución.

# si ya estas en el directorio del proyecto no es necesario cambiar de directorio, solo ejecutar el script correspondiente ./instalar_tarea.ps1 o .\instalar_tarea_con_ventana.ps1
```

**El script automáticamente:**
- ✅ Crea Tarea Programada "Scanner Connector API" o "Scanner Connector API With Console"
- ✅ Configura inicio automático al iniciar sesión (solo en modo sin ventana)
- ✅ Usa `pythonw.exe` (sin ventana) o `python.exe` (con ventana)
- ✅ Configura auto-reinicio (5 intentos, 1 min entre cada uno)
- ✅ Inicia el servicio inmediatamente
- ✅ Verifica que esté funcionando

**Comandos de control:**

```powershell
# Ver estado
Get-ScheduledTask -TaskName "tarea conector"

# Iniciar
Start-ScheduledTask -TaskName "tarea conector"

# Detener
Stop-ScheduledTask -TaskName "tarea conector"

# Ver logs
Get-Content logs\api_production.log -Tail 50

# Verificar proceso
Get-Process pythonw
```

---

### **🖱️ Acceso Directo en el Escritorio** (Recomendado para facilitar el inicio)

Para simplificar el inicio del servidor, puedes crear un acceso directo en el escritorio:

#### **Prerequisito:**
Primero debes haber ejecutado **una vez** el script `instalar_tarea_con_ventana.ps1` para crear la tarea programada. porque el script de acceso directo solo inicia la tarea, no la crea, si la tarea no existe, te pedirá que ejecutes primero el script de instalación con ventana.

#### **Crear acceso directo manualmente:**

1. **Clic derecho en el Escritorio** → Nuevo → Acceso directo

2. **En "Ubicación del elemento"**, pega (ajusta la ruta si es diferente):
   ```
   C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe -ExecutionPolicy Bypass -File "C:\Proyectos\scanner_connector_polihc_basic\iniciar_servidor.ps1"
   ```

3. **Clic en "Siguiente"**

4. **Nombre del acceso directo:** (puedes usar emojis si quieres)
   ```
   🚀 Iniciar Scanner Server
   ```

5. **Clic en "Finalizar"**

6. **Clic derecho en el acceso directo recién creado** → Propiedades

7. **En la pestaña "Acceso directo":**
   - Clic en botón **"Avanzadas..."** (esquina inferior derecha)
   - ✅ Marcar **"Ejecutar como administrador"**
   - Aplicar → Aceptar

8. **(Opcional) Cambiar icono:**
   - Propiedades → Cambiar icono
   - Elige uno de servidor/engranaje del sistema
   - O busca iconos personalizados en `C:\Windows\System32\imageres.dll`

#### **Crear acceso directo con PowerShell (automático):**
```powershell
# Como Administrador
$WshShell = New-Object -comObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut("$env:USERPROFILE\Desktop\Iniciar Scanner Server.lnk")
$Shortcut.TargetPath = "C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
$Shortcut.Arguments = '-ExecutionPolicy Bypass -File "C:\Proyectos\scanner_connector_polihc_basic\iniciar_servidor.ps1"'
$Shortcut.WorkingDirectory = "C:\Proyectos\scanner_connector_polihc_basic"
$Shortcut.WindowStyle = 1
$Shortcut.Save()

Write-Host "✅ Acceso directo creado en el escritorio" -ForegroundColor Green
Write-Host "⚠️  Haz clic derecho → Propiedades → Avanzadas → Marcar 'Ejecutar como administrador'" -ForegroundColor Yellow
```

#### **Uso del acceso directo:**

1. **Doble clic** en el acceso directo del escritorio
2. **Confirmar permisos** de administrador (UAC)
3. ✅ El script verificará si la tarea existe y si el servidor ya está corriendo
4. ✅ Si todo está bien, iniciará el servidor con ventana de logs
5. ✅ Para detener: **Ctrl+C** en la ventana o `Stop-ScheduledTask` desde PowerShell Admin

#### **Notas importantes:**

- ✅ El acceso directo **NO reinstala** la tarea cada vez (solo la inicia)
- ✅ Si el servidor ya está corriendo, te avisará y no hará nada
- ✅ Si la tarea no existe, te pedirá que ejecutes primero `instalar_tarea_con_ventana.ps1`
- ✅ Es más rápido y sencillo que abrir PowerShell manualmente

---

### **🧹 Limpieza Automática de Logs**

Para evitar que los logs crezcan indefinidamente, instala la tarea de limpieza:

```powershell
# Como Administrador
cd C:\Proyectos\scanner_connector_polihc_basic
.\instalar_tarea_limpiar_logs.ps1

.\instalar_tarea_limpiar_logs.ps1
```

**Configuración de Limpieza:**
- 📅 **Ejecución**: Cada martes a las 10:00 AM
- 🗑️ **Elimina**: Logs operativos (`*.log`) en cada ejecución semanal
- 📝 **Mantiene**: Reporte mensual `cleanup_audit.txt` (gestionado por auditoría)
- 📄 **Genera**: `resumen_limpieza_*.log` por ejecución
- 🔄 **Auto-reinicio**: 2 intentos cada 10 minutos si falla

**Archivos que limpia:**
- `api_production.log`
- Todos los archivos `.log` en la carpeta `logs/`

**Comandos útiles:**

```powershell
# Ver estado de la tarea
Get-ScheduledTask -TaskName "tarea limpiar logs"

# Ejecutar limpieza manualmente (ahora)
Start-ScheduledTask -TaskName "tarea limpiar logs"

# Ver resultado (último log de limpieza)
Get-Content logs\resumen_limpieza_*.log -Tail 30 | Sort-Object -Descending | Select-Object -First 30

# Desinstalar tarea
Unregister-ScheduledTask -TaskName "tarea limpiar logs"
```

---

### **Opción B: Servicio Windows con NSSM** (No recomendado para TWAIN)

> ⚠️ **Limitación**: NSSM corre en Session 0, TWAIN requiere sesión de usuario, por lo que el escaneo NO funcionará.

Solo usar si NO necesitas escanear (solo para API de prueba):

```powershell
# Descargar NSSM
# https://nssm.cc/download

# Instalar servicio
nssm install ScannerConnectorAPI "C:\Proyectos\scanner_connector_polihc_basic\venv\Scripts\pythonw.exe" "C:\Proyectos\scanner_connector_polihc_basic\run_production.py"
nssm set ScannerConnectorAPI AppDirectory "C:\Proyectos\scanner_connector_polihc_basic"
nssm start ScannerConnectorAPI
```

---

## 🔧 Paso 6: Configuración Adicional

### **6.1 Auditoría de Seguridad Automática**

```powershell
# Como Administrador
.\instalar_tarea_auditoria.ps1
```

Esto configura:
- ✅ Auditoría semanal (martes 9:00 AM)
- ✅ Solo reporte de vulnerabilidades (sin actualización automática)
- ✅ Reporte consolidado en `logs\cleanup_audit.txt`

### **6.2 Configuración de Red**

No se requiere configuración de red, firewall, IP estática ni Tailscale. El sistema opera solo en modo local.

---

## 🐛 Solución de Problemas

### ❌ Error: "Python no es de 32 bits"

```powershell
# Verificar arquitectura
python -c "import struct; print(struct.calcsize('P') * 8)"

# Si muestra 64, desinstalar y reinstalar Python 32 bits
```

### ❌ Error: "No se pudo inicializar TWAIN"

**Causas comunes:**
1. Python no es 32 bits
2. Driver TWAIN no instalado
3. Escáner apagado/desconectado

**Solución:**
```powershell
# Verificar driver
python -c "import twain; sm = twain.SourceManager(0); print(sm.GetSourceList())"

# Si falla, reinstalar driver TWAIN
# Verificar que la carpeta Toshiba e-estudio Scan Editor exista en Archivos de Programa (x86) 
# y que en dispositivos e impresoras aparezca el escáner
```

### ❌ Error: "SECRET_KEY no configurada"

```powershell
# Verificar que .env existe
Test-Path .env

# Si no existe, copiar plantilla
Copy-Item .env.example .env

# Generar SECRET_KEY
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### ❌ Error: "Puerto 5000 ya está en uso"

```powershell
# Ver qué proceso usa el puerto
netstat -ano | findstr :5000

# Matar proceso (reemplaza PID), el pid es el número que aparece al final del comando anterior
taskkill /PID 12345 /F
```

### ❌ Tarea Programada no inicia

```powershell
# Ver información de última ejecución
Get-ScheduledTaskInfo -TaskName "tarea conector con ventana"

# Si Task Scheduler no tiene eventos, ver todos los errores recientes del sistema
Get-EventLog -LogName Application -EntryType Error -Newest 10 | Format-Table TimeGenerated, Source, Message -AutoSize

# Verificar que pythonw.exe existe, si asi no es la ruta, ajustar en el script de instalación, o cuando se este ejecutando el comando
Test-Path "C:\Proyectos\scanner_connector_polihc_basic\venv\Scripts\pythonw.exe"
```

---

## 📊 Checklist Final

### **Antes de desconectar USB**

- [ ] Proyecto copiado a USB
- [ ] Python 32 bits instalado y verificado
- [ ] Driver TWAIN Toshiba instalado y escáner detectado (Scan Editor OK)
- [ ] Driver TWAIN Savin instalado (si aplica)
- [ ] Tesseract OCR instalado (opcional)
- [ ] Git instalado
- [ ] Configuración local confirmada (sin Tailscale ni acceso remoto)
- [ ] Proyecto copiado a `C:\Proyectos\scanner_connector_polihc_basic`
- [ ] Entorno virtual creado y activado
- [ ] Dependencias instaladas (`pip install -r requirements.txt`)
- [ ] Archivo `.env` configurado con SECRET_KEY
- [ ] SCANNER_NAME verificado y configurado
- [ ] No se requiere regla de firewall (modo local)
- [ ] Prueba manual exitosa (`python app.py`)
- [ ] Prueba con Waitress exitosa (`python run_production.py`)
- [ ] Tarea Programada instalada y funcionando
- [ ] Health check responde: `curl http://localhost:5000/api/scan/health`
- [ ] Check-scanner responde: `curl http://localhost:5000/api/scan/check-scanner`

### **Verificación Final**

```powershell
# 1. Verificar servicio corriendo
Get-Process pythonw

# 2. Probar endpoints
curl http://localhost:5000/api/scan/health
curl http://localhost:5000/api/scan/check-scanner

# 3. Ver logs recientes
Get-Content logs\api_production.log -Tail 20

# 4. Verificar tarea programada
Get-ScheduledTask -TaskName "tarea conector con ventana" | Select-Object State, LastRunTime, NextRunTime
```

---

## 📞 Soporte Post-Instalación

### **Logs Importantes**

| Archivo | Ubicación | Propósito |
|---------|-----------|-----------|
| `api_production.log` | `logs/` | Logs de la API |
| `cleanup_audit.txt` | `logs/` | Reporte mensual consolidado de auditoría |
| Windows Event Log | Event Viewer → Application | Errores de Tarea Programada |

### **Comandos Útiles**

```powershell
# Ver estado completo
Get-ScheduledTask -TaskName "tarea conector con ventana" | Format-List *

# Reiniciar servicio
Stop-ScheduledTask -TaskName "tarea conector con ventana"
Start-Sleep -Seconds 3
Start-ScheduledTask -TaskName "tarea conector con ventana"

# Ver procesos Python
Get-Process python*

# Limpiar logs antiguos
Remove-Item logs\*.log.* -Force
```

---

## 📋 Comandos Avanzados de Administración

### **Ver todas las tareas programadas del proyecto**

```powershell
# Listar todas las tareas relacionadas con Scanner Connector
Get-ScheduledTask | Where-Object { $_.TaskName -like "*Scanner*" } | Format-Table TaskName, State, LastRunTime, NextRunTime -AutoSize

# Ver detalles completos de una tarea específica
Get-ScheduledTaskInfo -TaskName "tarea conector"
Get-ScheduledTaskInfo -TaskName "tarea conector con ventana"
Get-ScheduledTaskInfo -TaskName "tarea auditoria"
Get-ScheduledTaskInfo -TaskName "tarea limpiar logs"
```

### **Ver detalles de procesos Python**

```powershell
# Información básica mejorada
Get-Process python* | Select-Object `
    Id, 
    ProcessName, 
    @{Name="CPU(s)";Expression={[math]::Round($_.CPU,2)}}, 
    @{Name="Memory(MB)";Expression={[math]::Round($_.WorkingSet/1MB,2)}}, 
    @{Name="Uptime";Expression={(New-TimeSpan -Start $_.StartTime).ToString("hh\:mm\:ss")}},
    StartTime,
    Path | Format-Table -AutoSize

# Ver detalles completos incluyendo argumentos
Get-WmiObject Win32_Process -Filter "name like 'python%'" | Select-Object `
    ProcessId,
    Name,
    @{Name="Memory(MB)";Expression={[math]::Round($_.WorkingSetSize/1MB,2)}},
    CreationDate,
    CommandLine | Format-List

# Ver relación padre-hijo (útil para verificar que no hay duplicados)
Get-WmiObject Win32_Process -Filter "name like 'python%'" | Select-Object ProcessId, ParentProcessId, CommandLine | Format-List
```

### **Ver logs del Task Scheduler**

```powershell
# Ver eventos del Task Scheduler (últimos 10)
Get-WinEvent -LogName "Microsoft-Windows-TaskScheduler/Operational" -MaxEvents 10 | Format-Table TimeCreated, Id, Message -Wrap

# Filtrar solo errores del Task Scheduler
Get-WinEvent -LogName "Microsoft-Windows-TaskScheduler/Operational" -MaxEvents 50 | Where-Object { $_.LevelDisplayName -eq "Error" } | Format-Table TimeCreated, Id, Message -Wrap

# Buscar eventos relacionados con tus tareas
Get-WinEvent -LogName "Microsoft-Windows-TaskScheduler/Operational" -MaxEvents 100 | Where-Object { $_.Message -like "*tarea*" } | Format-Table TimeCreated, Id, Message -Wrap

# Ver errores recientes del sistema (si Task Scheduler no tiene eventos)
Get-EventLog -LogName Application -EntryType Error -Newest 10 | Format-Table TimeGenerated, Source, Message -AutoSize
```

### **Control completo de las 4 tareas programadas**

#### **1. Scanner Connector API (sin ventana)**
```powershell
# Instalar
.\instalar_tarea.ps1

# Ver estado
Get-ScheduledTask -TaskName "tarea conector"

# Iniciar
Start-ScheduledTask -TaskName "tarea conector"

# Detener
Stop-ScheduledTask -TaskName "tarea conector"

# Ver última ejecución
Get-ScheduledTaskInfo -TaskName "tarea conector"

# Eliminar
Unregister-ScheduledTask -TaskName "tarea conector" -Confirm:$false
```

#### **2. Scanner Connector API (con ventana)**
```powershell
# Instalar
.\instalar_tarea_con_ventana.ps1

# Ver estado
Get-ScheduledTask -TaskName "tarea conector con ventana"

# Iniciar
Start-ScheduledTask -TaskName "tarea conector con ventana"

# Detener
Stop-ScheduledTask -TaskName "tarea conector con ventana"

# Eliminar
Unregister-ScheduledTask -TaskName "tarea conector con ventana" -Confirm:$false
```

#### **3. Auditoría de Seguridad**
```powershell
# Instalar
.\instalar_tarea_auditoria.ps1

# Ver estado
Get-ScheduledTask -TaskName "tarea auditoria"

# Ejecutar auditoría manualmente
Start-ScheduledTask -TaskName "tarea auditoria"

# Ver logs de auditoría
Get-Content logs\cleanup_audit.txt -Tail 80

# Eliminar
Unregister-ScheduledTask -TaskName "tarea auditoria" -Confirm:$false
```

#### **4. Limpieza de Logs**
```powershell
# Instalar
.\instalar_tarea_limpiar_logs.ps1

# Ver estado
Get-ScheduledTask -TaskName "tarea limpiar logs"

# Ejecutar limpieza manualmente
Start-ScheduledTask -TaskName "tarea limpiar logs"

# Ver resultado (último log de limpieza)
Get-Content logs\resumen_limpieza_*.log -Tail 30 | Sort-Object -Descending | Select-Object -First 30

# Ver logs recientes
Get-Content logs\api_production.log -Tail 20
Get-Content logs\cleanup_audit.txt -Tail 20

# Eliminar
Unregister-ScheduledTask -TaskName "tarea limpiar logs" -Confirm:$false
```

### **Comandos de diagnóstico**

```powershell
# Verificar que Python es 32 bits
python -c "import struct; print('Arquitectura:', struct.calcsize('P') * 8, 'bits')"

# Verificar TWAIN
python -c "import twain; print('✅ TWAIN instalado correctamente')"

# Listar escáneres disponibles
python -c "from utils.list_scanners import list_scanners; print(list_scanners())"

# Ver qué está usando el puerto 5000
netstat -ano | findstr :5000

# Matar proceso por PID (reemplaza 12345 con el PID real)
taskkill /PID 12345 /F

# Matar todos los procesos Python
Stop-Process -Name python -Force

# Ver espacio en disco usado por logs
Get-ChildItem logs -Recurse | Measure-Object -Property Length -Sum | Select-Object @{Name="Size(MB)";Expression={[math]::Round($_.Sum/1MB,2)}}

# Listar todos los archivos .log con su tamaño
Get-ChildItem logs\*.log | Select-Object Name, @{Name="Size(MB)";Expression={[math]::Round($_.Length/1MB,2)}}, LastWriteTime | Format-Table -AutoSize
```

### **Comandos de emergencia**

```powershell
# Detener TODAS las tareas del proyecto
Get-ScheduledTask | Where-Object { $_.TaskName -like "*tarea*" } | ForEach-Object { Stop-ScheduledTask -TaskName $_.TaskName }

# Reiniciar TODAS las tareas del proyecto
Get-ScheduledTask | Where-Object { $_.TaskName -like "*tarea*" } | ForEach-Object { 
    Stop-ScheduledTask -TaskName $_.TaskName -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
    Start-ScheduledTask -TaskName $_.TaskName
}

# Eliminar TODAS las tareas del proyecto (usar con precaución)
Get-ScheduledTask | Where-Object { $_.TaskName -like "*tarea*" } | ForEach-Object { 
    Unregister-ScheduledTask -TaskName $_.TaskName -Confirm:$false
}

# Limpiar todos los procesos Python (usar con precaución)
Get-Process python* | Stop-Process -Force

# Reinicio completo del servicio
Stop-ScheduledTask -TaskName "tarea conector con ventana" -ErrorAction SilentlyContinue
Stop-Process -Name python -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 3
Start-ScheduledTask -TaskName "tarea conector con ventana"
```

---
# Como Administrador para llegar al proyecto rápidamente (cambiarlo según sea necesario)
cd C:\Users\user1\Documents\Proyectos\scanner_connector_polihc_basic

**Proyecto listo para transferir y desplegar en nuevo PC**
