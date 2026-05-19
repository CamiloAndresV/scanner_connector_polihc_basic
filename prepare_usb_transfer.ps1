# prepare_usb_transfer.ps1
# Script para preparar el proyecto Scanner Connector API para transferencia USB
# Ejecutar desde la raíz del proyecto: .\prepare_usb_transfer.ps1

param(
    [Parameter(Mandatory=$false)]
    # Asegurarse de cambiar la letra de unidad si es necesario
    [string]$DestinoUSB = "E:\scanner_connector_polihc_basic"
)

Write-Host "`n============================================================" -ForegroundColor Cyan
Write-Host "  PREPARACIÓN USB - Scanner Connector API" -ForegroundColor Cyan
Write-Host "============================================================`n" -ForegroundColor Cyan

# Verificar que estamos en la raíz del proyecto
if (-not (Test-Path "app.py")) {
    Write-Host "❌ Error: Ejecutar desde la raíz del proyecto" -ForegroundColor Red
    Write-Host "   EJEMPLO: cd C:\Users\ospin\Clonaciones\scanner_connector_polihc_basic" -ForegroundColor Yellow
    exit 1
}

$proyectoActual = Get-Location

Write-Host "📁 Proyecto origen: $proyectoActual" -ForegroundColor White
Write-Host "💾 Destino USB: $DestinoUSB`n" -ForegroundColor White

# Verificar que la unidad USB es accesible
$driveLetter = $DestinoUSB.Substring(0, 2)  # Extraer letra de unidad (ej: "E:")
Write-Host "🔍 Verificando acceso a la unidad $driveLetter..." -ForegroundColor Yellow

if (-not (Test-Path $driveLetter)) {
    Write-Host "`n❌ Error: La unidad USB no está disponible" -ForegroundColor Red
    Write-Host "   Unidad esperada: $driveLetter" -ForegroundColor Yellow
    Write-Host "   Por favor, verifica que:" -ForegroundColor Yellow
    Write-Host "     • El USB esté conectado correctamente" -ForegroundColor Gray
    Write-Host "     • La letra de unidad sea correcta (se esperaba: $driveLetter)" -ForegroundColor Gray
    Write-Host "     • El USB esté reconocido por Windows`n" -ForegroundColor Gray
    
    # Mostrar unidades disponibles
    Write-Host "💿 Unidades disponibles en este equipo:" -ForegroundColor Cyan
    $drives = Get-PSDrive -PSProvider FileSystem | Where-Object { $_.Root -match '^[A-Z]:\\' }
    foreach ($drive in $drives) {
        $letter = $drive.Name
        $used = [math]::Round(($drive.Used / 1GB), 2)
        $free = [math]::Round(($drive.Free / 1GB), 2)
        Write-Host "   • $letter`: ($used GB usado, $free GB libre)" -ForegroundColor Gray
    }
    
    Write-Host "`n💡 Soluciones:" -ForegroundColor Cyan
    Write-Host "   1. Ejecutar de nuevo con parámetro: .\prepare_usb_transfer.ps1 -DestinoUSB 'D:\scanner_connector_polihc_basic'" -ForegroundColor Gray
    Write-Host "   2. O conectar USB en $driveLetter y esperar a que Windows lo reconozca`n" -ForegroundColor Gray
    exit 1
}

Write-Host "✅ Unidad USB accesible: $driveLetter`n" -ForegroundColor Green

# Crear carpeta destino
Write-Host "📂 Creando carpeta en USB..." -ForegroundColor Yellow
try {
    New-Item -ItemType Directory -Path $DestinoUSB -Force | Out-Null
} catch {
    Write-Host "`n❌ Error: No se puede crear la carpeta en USB" -ForegroundColor Red
    Write-Host "   Ruta: $DestinoUSB" -ForegroundColor Yellow
    Write-Host "   Error: $($_.Exception.Message)`n" -ForegroundColor Gray
    Write-Host "💡 Posibles causas:" -ForegroundColor Cyan
    Write-Host "   • Permisos insuficientes en la unidad" -ForegroundColor Gray
    Write-Host "   • USB protegido contra escritura" -ForegroundColor Gray
    Write-Host "   • Espacio insuficiente en el USB`n" -ForegroundColor Gray
    exit 1
}

# Archivos esenciales a copiar
$archivosEsenciales = @(
    "app.py",
    "run_production.py",
    "run_with_console.py",
    "requirements.txt",
    ".env.example",
    ".env",
    ".gitignore",
    "README.md",
    "pytest.ini",
    "instalar_tarea.ps1",
    "instalar_tarea_con_ventana.ps1",
    "iniciar_servidor.ps1",
    "instalar_tarea_auditoria.ps1",
    "instalar_tarea_limpiar_logs.ps1",
    "prepare_usb_transfer.ps1",
    "PRD.md",
    "AUDITORIA_SEGURIDAD.md",
    "usb_transfer_guide.md",
    "context.txt"
)

Write-Host "📄 Copiando archivos esenciales..." -ForegroundColor Yellow
foreach ($archivo in $archivosEsenciales) {
    if (Test-Path $archivo) {
        Copy-Item -Path $archivo -Destination $DestinoUSB -Force
        Write-Host "  ✅ $archivo" -ForegroundColor Green
    } else {
        Write-Host "  ⚠️  $archivo (no encontrado, omitido)" -ForegroundColor Yellow
    }
}

# Carpetas a copiar (excluyendo archivos innecesarios)
$carpetas = @("config", "controllers", "services", "utils", "test", "scripts", ".github")

Write-Host "`n📁 Copiando carpetas del proyecto..." -ForegroundColor Yellow
foreach ($carpeta in $carpetas) {
    if (Test-Path $carpeta) {
        # Copiar excluyendo __pycache__ y .pyc
        Copy-Item -Path $carpeta -Destination $DestinoUSB -Recurse -Force -Exclude "__pycache__", "*.pyc", "*.pyo"
        
        # Limpiar __pycache__ del destino si quedó alguno (PowerShell 5.1 compatible)
        Get-ChildItem -Path "$DestinoUSB\$carpeta" -Recurse | Where-Object { $_.PSIsContainer -and $_.Name -eq "__pycache__" } | Remove-Item -Recurse -Force
        
        Write-Host "  ✅ $carpeta\" -ForegroundColor Green
    } else {
        Write-Host "  ⚠️  $carpeta\ (no encontrado, omitido)" -ForegroundColor Yellow
    }
}

# Carpetas logs/ y scans/ NO se copian - se crean automáticamente al ejecutar
# - run_production.py y run_with_console.py crean logs/ al iniciar
# - config/config.py crea scans/ al importar configuración
# Esto simplifica la transferencia y evita copiar carpetas vacías innecesarias

# Verificar que NO se copiaron archivos sensibles
Write-Host "`n🔒 Verificando seguridad..." -ForegroundColor Yellow
$archivosSensibles = @("scanner_session.lock")
$problemasSeguridad = $false

foreach ($archivo in $archivosSensibles) {
    if (Test-Path "$DestinoUSB\$archivo") {
        Write-Host "  ❌ ADVERTENCIA: $archivo fue copiado (contiene secretos)" -ForegroundColor Red
        Remove-Item "$DestinoUSB\$archivo" -Force
        Write-Host "     → Eliminado automáticamente" -ForegroundColor Yellow
        $problemasSeguridad = $true
    }
}

if (-not $problemasSeguridad) {
    Write-Host "  ✅ No se copiaron archivos sensibles" -ForegroundColor Green
}

# Verificar que NO se copiaron carpetas innecesarias
Write-Host "`n🧹 Verificando limpieza..." -ForegroundColor Yellow
$carpetasInnecesarias = @("venv", ".git", ".pytest_cache", "__pycache__", "dev_tools", "testsprite_tests", "htmlcov", ".coverage")
$carpetasEncontradas = $false

foreach ($carpeta in $carpetasInnecesarias) {
    if (Test-Path "$DestinoUSB\$carpeta") {
        Write-Host "  ⚠️  $carpeta\ fue copiado (innecesario)" -ForegroundColor Yellow
        Remove-Item "$DestinoUSB\$carpeta" -Recurse -Force
        Write-Host "     → Eliminado automáticamente" -ForegroundColor Yellow
        $carpetasEncontradas = $true
    }
}

if (-not $carpetasEncontradas) {
    Write-Host "  ✅ No se copiaron carpetas innecesarias" -ForegroundColor Green
}

# README_USB.txt ya NO es necesario - usb_transfer_guide.md es más completo
# Se eliminó para evitar duplicación de documentación

# Generar reporte de transferencia
Write-Host "`n📊 Generando reporte..." -ForegroundColor Yellow

$archivosCopiados = Get-ChildItem -Path $DestinoUSB -Recurse | Where-Object { -not $_.PSIsContainer }
$totalArchivos = $archivosCopiados.Count
$totalTamano = ($archivosCopiados | Measure-Object -Property Length -Sum).Sum / 1MB

$reporte = @"
================================================================================
  REPORTE DE TRANSFERENCIA USB - Scanner Connector API
================================================================================

Fecha: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")
Origen: $proyectoActual
Destino: $DestinoUSB

📊 ESTADÍSTICAS:
  • Total archivos: $totalArchivos
  • Tamaño total: $([math]::Round($totalTamano, 2)) MB

✅ ARCHIVOS INCLUIDOS:
  • Código fuente (app.py, run_production.py, run_with_console.py)
  • Módulos (controllers/, services/, utils/, scripts/)
  • Configuración (.env, .env.example, .gitignore, requirements.txt)
  • Scripts de instalación:
    - instalar_tarea.ps1 (sin ventana)
    - instalar_tarea_con_ventana.ps1 (con ventana visible, Ctrl+C habilitado)
    - iniciar_servidor.ps1 (para acceso directo de escritorio)
  • Tareas programadas:
    - instalar_tarea_auditoria.ps1 (martes 9 AM)
    - instalar_tarea_limpiar_logs.ps1 (viernes 8 AM)
  • Scripts Python:
    - scripts/security_audit.py (auditoría de seguridad)
    - scripts/limpiar_logs.py (limpieza automática, 6 días/10 MB)
  • Preparación USB (prepare_usb_transfer.ps1)
  • Documentación completa:
    - usb_transfer_guide.md (GUÍA PRINCIPAL DE INSTALACIÓN)
    - README.md (documentación del proyecto)
    - PRD.md (especificaciones de producción)
    - AUDITORIA_SEGURIDAD.md (informe de seguridad)
  • Tests (test/)

❌ ARCHIVOS EXCLUIDOS:
  • Entorno virtual (venv/)
  • Archivos compilados (__pycache__/, *.pyc)
  • Logs antiguos (logs/*.log)
  • Archivos temporales (scans/*)
  • Historial Git (.git/)

🚀 MEJORAS RECIENTES INCLUIDAS:
  ✓ Ctrl+C habilitado en run_with_console.py (cierre rápido)
  ✓ Script iniciar_servidor.ps1 (para acceso directo en escritorio)
  ✓ Limpieza de logs en Python (consistencia con proyecto)
  ✓ Documentación actualizada con instrucciones de acceso directo

📋 TAREAS PROGRAMADAS DISPONIBLES:
  1. Servidor API (inicio automático al login)
  2. Auditoría de seguridad (semanal, martes 9 AM)
  3. Limpieza de logs (semanal, viernes 8 AM)

🎯 PRÓXIMOS PASOS:
  1. Verificar que USB tiene al menos $([math]::Ceiling($totalTamano)) MB libres
  2. Copiar carpeta a PC destino: C:\Proyectos\scanner_connector_polihc_basic
  3. Seguir instrucciones en usb_transfer_guide.md (GUÍA PRINCIPAL)
  4. Opcional: Crear acceso directo de escritorio (ver guía)

⚠️ RECORDATORIOS IMPORTANTES:
  • Python debe ser 32 bits (TWAIN requiere 32 bits)
  • Instalar driver TWAIN del escáner Toshiba
  • Configurar .env con SECRET_KEY antes de usar
  • Reinstalar tarea de limpieza si actualizas desde versión antigua

================================================================================
"@

$reporte | Out-File -FilePath "$DestinoUSB\TRANSFER_REPORT.txt" -Encoding utf8

# Mostrar resumen final
Write-Host "`n============================================================" -ForegroundColor Cyan
Write-Host "  ✅ TRANSFERENCIA PREPARADA EXITOSAMENTE" -ForegroundColor Green
Write-Host "============================================================`n" -ForegroundColor Cyan

Write-Host "📊 Resumen:" -ForegroundColor White
Write-Host "  • Archivos copiados: $totalArchivos" -ForegroundColor Gray
Write-Host "  • Tamaño total: $([math]::Round($totalTamano, 2)) MB" -ForegroundColor Gray
Write-Host "  • Ubicación: $DestinoUSB`n" -ForegroundColor Gray

Write-Host "📋 Archivos de ayuda creados:" -ForegroundColor White
Write-Host "  • TRANSFER_REPORT.txt - Reporte detallado de transferencia" -ForegroundColor Gray
Write-Host "  • usb_transfer_guide.md - Guía completa de instalación`n" -ForegroundColor Gray

Write-Host "🎯 Próximos pasos:" -ForegroundColor White
Write-Host "  1. Verificar contenido en: $DestinoUSB" -ForegroundColor Gray
Write-Host "  2. Expulsar USB de forma segura" -ForegroundColor Gray
Write-Host "  3. Conectar USB en PC destino" -ForegroundColor Gray
Write-Host "  4. Seguir instrucciones en usb_transfer_guide.md (GUÍA PRINCIPAL)`n" -ForegroundColor Gray

Write-Host "✅ Listo para transferir!" -ForegroundColor Green
Write-Host ""
