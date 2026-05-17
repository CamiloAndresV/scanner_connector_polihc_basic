# instalar_tarea.ps1
# Script de instalación de Tarea Programada para Scanner Connector API
# Ejecutar como Administrador: .\instalar_tarea.ps1
# ============================================================================

# Verificar que se ejecuta como Administrador
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "`n❌ Este script debe ejecutarse como Administrador" -ForegroundColor Red
    Write-Host "   Haz clic derecho en PowerShell → 'Ejecutar como administrador'" -ForegroundColor Yellow
    pause
    exit 1
}

# Configuración
$taskName = "tarea conector"
$projectPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonwPath = Join-Path $projectPath "venv\Scripts\pythonw.exe"
$scriptPath = Join-Path $projectPath "run_production.py"
$currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$userName = $env:USERNAME

Write-Host "`n" -NoNewline
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  INSTALADOR - Scanner Connector API (Tarea Programada)" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "`n📁 Proyecto: $projectPath" -ForegroundColor White
Write-Host "👤 Usuario: $currentUser" -ForegroundColor White

# Verificar que existe pythonw.exe
if (-not (Test-Path $pythonwPath)) {
    Write-Host "`n❌ No se encontró pythonw.exe en:" -ForegroundColor Red
    Write-Host "   $pythonwPath" -ForegroundColor Yellow
    Write-Host "`n   Verifica que el entorno virtual esté creado correctamente." -ForegroundColor Yellow
    pause
    exit 1
}

# Verificar que existe run_production.py
if (-not (Test-Path $scriptPath)) {
    Write-Host "`n❌ No se encontró run_production.py en:" -ForegroundColor Red
    Write-Host "   $scriptPath" -ForegroundColor Yellow
    pause
    exit 1
}

Write-Host "`n✅ Archivos verificados correctamente" -ForegroundColor Green

# Detener y eliminar tarea existente
Write-Host "`n🔄 Limpiando tarea anterior si existe..." -ForegroundColor Yellow
Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

# Crear componentes de la tarea
Write-Host "📝 Configurando tarea programada..." -ForegroundColor Yellow

$action = New-ScheduledTaskAction `
    -Execute $pythonwPath `
    -Argument "`"$scriptPath`"" `
    -WorkingDirectory $projectPath

$trigger = New-ScheduledTaskTrigger -AtLogOn -User $userName

$principal = New-ScheduledTaskPrincipal `
    -UserId $currentUser `
    -LogonType Interactive `
    -RunLevel Highest

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 5 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Days 0) `
    -MultipleInstances IgnoreNew `
    -Priority 4

# Registrar tarea
Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Description "Scanner Connector API - Produccion (pythonw, auto-restart, sin ventana)" `
    -Force | Out-Null

Write-Host "✅ Tarea programada registrada" -ForegroundColor Green

# Iniciar tarea
Write-Host "`n🚀 Iniciando servicio..." -ForegroundColor Yellow
Start-ScheduledTask -TaskName $taskName
Start-Sleep -Seconds 5

# Verificar proceso
$proc = Get-Process pythonw -ErrorAction SilentlyContinue
if ($proc) {
    Write-Host "✅ Proceso pythonw corriendo (PID: $($proc.Id))" -ForegroundColor Green
} else {
    Write-Host "⚠️  Proceso no detectado inmediatamente, verificando API..." -ForegroundColor Yellow
}

# Probar endpoint
Write-Host "`n🔍 Probando conexión con la API..." -ForegroundColor Yellow
Start-Sleep -Seconds 2

try {
    $response = Invoke-WebRequest -Uri "http://localhost:5000/api/scan/health" -UseBasicParsing -TimeoutSec 10
    $content = $response.Content | ConvertFrom-Json
    Write-Host "✅ API respondiendo correctamente" -ForegroundColor Green
    Write-Host "   Status: $($content.status)" -ForegroundColor White
} catch {
    Write-Host "⚠️  API aún no responde. Puede tardar unos segundos más." -ForegroundColor Yellow
    Write-Host "   Verifica con: Get-Content `"$projectPath\logs\api_production.log`" -Tail 20" -ForegroundColor Yellow
}

# Resumen final
Write-Host "`n============================================================" -ForegroundColor Cyan
Write-Host "  INSTALACIÓN COMPLETADA" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "`n📋 Comandos útiles:" -ForegroundColor White
Write-Host "   • Ver estado:    Get-ScheduledTask -TaskName `"$taskName`"" -ForegroundColor Gray
Write-Host "   • Iniciar:       Start-ScheduledTask -TaskName `"$taskName`"" -ForegroundColor Gray
Write-Host "   • Detener:       Stop-ScheduledTask -TaskName `"$taskName`"" -ForegroundColor Gray
Write-Host "   • Ver logs:      Get-Content `"$projectPath\logs\api_production.log`" -Tail 50" -ForegroundColor Gray
Write-Host "   • Probar API:    curl http://localhost:5000/api/scan/health" -ForegroundColor Gray
Write-Host "`n⚠️  IMPORTANTE: La API se iniciará automáticamente cada vez que" -ForegroundColor Yellow
Write-Host "   el usuario '$userName' inicie sesión en Windows." -ForegroundColor Yellow
Write-Host ""
pause
