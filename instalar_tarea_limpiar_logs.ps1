# instalar_tarea_limpiar_logs.ps1
# Instalador de Tarea Programada para Limpieza de Logs
# Ejecutar como Administrador: .\instalar_tarea_limpiar_logs.ps1
# ============================================================================

# Verificar permisos de Administrador
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "`nERROR: Ejecutar como Administrador" -ForegroundColor Red
    pause
    exit 1
}

# Configuración
$taskName = "tarea limpiar logs"
$projectPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonPath = Join-Path $projectPath "venv\Scripts\python.exe"
$scriptPath = Join-Path $projectPath "scripts\limpiar_logs.py"
$currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name

Write-Host "`n============================================================" -ForegroundColor Cyan
Write-Host "  Instalador - Limpieza Automatica de Logs" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# Verificar script
if (-not (Test-Path $scriptPath)) {
    Write-Host "`nERROR: Script no encontrado: $scriptPath" -ForegroundColor Red
    pause
    exit 1
}

# Verificar Python
if (-not (Test-Path $pythonPath)) {
    Write-Host "`nERROR: Python no encontrado: $pythonPath" -ForegroundColor Red
    Write-Host "Asegurese de que el entorno virtual este creado." -ForegroundColor Yellow
    pause
    exit 1
}

Write-Host "Archivos verificados correctamente" -ForegroundColor Green

# Eliminar tarea anterior
Write-Host "`nLimpiando tarea anterior..." -ForegroundColor Yellow
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

# Crear tarea programada
Write-Host "Configurando tarea..." -ForegroundColor Yellow

$action = New-ScheduledTaskAction `
    -Execute $pythonPath `
    -Argument "`"$scriptPath`"" `
    -WorkingDirectory $projectPath

# Ejecutar cada viernes a las 8:00 AM
# $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Friday -At 8am
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Tuesday -At 10am

$principal = New-ScheduledTaskPrincipal `
    -UserId $currentUser `
    -LogonType Interactive `
    -RunLevel Highest

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 2 `
    -RestartInterval (New-TimeSpan -Minutes 10) `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

# Registrar tarea
Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Description "Limpieza automatica de logs operativos cada martes a las 10:00 AM" `
    -Force | Out-Null

Write-Host "Tarea programada instalada correctamente" -ForegroundColor Green
Write-Host "`n📅 Programacion: Cada martes a las 10:00 AM (1 hora después de auditoría)" -ForegroundColor White
Write-Host "🔄 Auto-reinicio: 2 intentos cada 10 minutos si falla" -ForegroundColor White
Write-Host "`n📋 Estrategia de limpieza semanal:" -ForegroundColor Cyan
Write-Host "  1️⃣  LOGS OPERATIVOS (.log)" -ForegroundColor White
Write-Host "     • Se eliminan semanalmente para evitar acumulación" -ForegroundColor Gray
Write-Host "     • Incluye api_production.log y security_audit.log" -ForegroundColor Gray
Write-Host "     • Se genera resumen de limpieza en cada ejecución" -ForegroundColor Gray
Write-Host ""
Write-Host "  2️⃣  REPORTE MENSUAL DE AUDITORÍA" -ForegroundColor White
Write-Host "     • cleanup_audit.txt NO se elimina semanalmente" -ForegroundColor Gray
Write-Host "     • Su reinicio cada 30 días lo gestiona la auditoría" -ForegroundColor Gray
Write-Host "     • Conserva historial mensual de vulnerabilidades" -ForegroundColor Gray
Write-Host ""
Write-Host "  3️⃣  VENTAJAS DE ESTA ESTRATEGIA" -ForegroundColor Green
Write-Host "     ✅ Menor acumulación de logs operativos" -ForegroundColor Gray
Write-Host "     ✅ Reporte mensual único para auditoría" -ForegroundColor Gray
Write-Host "     ✅ Separación clara entre limpieza y seguridad" -ForegroundColor Gray
Write-Host "     ✅ Menor riesgo de saturar almacenamiento" -ForegroundColor Gray
Write-Host "`nComandos utiles:" -ForegroundColor White
Write-Host "  - Ver estado: Get-ScheduledTask -TaskName `"$taskName`"" -ForegroundColor Gray
Write-Host "  - Ejecutar ahora: Start-ScheduledTask -TaskName `"$taskName`"" -ForegroundColor Gray
Write-Host "  - Ver resumen: Get-Content logs\resumen_limpieza_*.log -Tail 40" -ForegroundColor Gray
Write-Host "  - Ver auditoría: Get-Content logs\cleanup_audit.txt -Tail 80" -ForegroundColor Gray
Write-Host "  - Desinstalar: Unregister-ScheduledTask -TaskName `"$taskName`"" -ForegroundColor Gray
Write-Host ""
pause
