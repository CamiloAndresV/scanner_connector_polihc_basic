# instalar_tarea_con_ventana.ps1
# Script de instalación de Tarea Programada CON VENTANA DE CONSOLA VISIBLE
# La ventana mostrará logs en tiempo real y NO podrá cerrarse accidentalmente
# Ejecutar como Administrador: .\instalar_tarea_con_ventana.ps1
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
$taskName = "tarea conector con ventana"
$projectPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonPath = Join-Path $projectPath "venv\Scripts\python.exe"  # ← python.exe (CON ventana)
$scriptPath = Join-Path $projectPath "run_with_console.py"     # ← Script con protección
$currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$userName = $env:USERNAME

Write-Host "`n" -NoNewline
Write-Host "════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  INSTALADOR - Scanner API (MODO VENTANA PROTEGIDA)" -ForegroundColor Cyan
Write-Host "════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "`n📁 Proyecto: $projectPath" -ForegroundColor White
Write-Host "👤 Usuario: $currentUser" -ForegroundColor White
Write-Host "🖥️  Modo: VENTANA VISIBLE con logs en tiempo real" -ForegroundColor Green

# Verificar que existe python.exe
if (-not (Test-Path $pythonPath)) {
    Write-Host "`n❌ No se encontró python.exe en:" -ForegroundColor Red
    Write-Host "   $pythonPath" -ForegroundColor Yellow
    Write-Host "`n   Verifica que el entorno virtual esté creado correctamente." -ForegroundColor Yellow
    pause
    exit 1
}

# Verificar que existe run_with_console.py
if (-not (Test-Path $scriptPath)) {
    Write-Host "`n❌ No se encontró run_with_console.py en:" -ForegroundColor Red
    Write-Host "   $scriptPath" -ForegroundColor Yellow
    Write-Host "`n   Este archivo debe existir para el modo ventana protegida." -ForegroundColor Yellow
    pause
    exit 1
}

Write-Host "`n✅ Archivos verificados correctamente" -ForegroundColor Green

# Detener y eliminar tarea existente
Write-Host "`n🔄 Limpiando tarea anterior si existe..." -ForegroundColor Yellow
Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

# Crear componentes de la tarea
Write-Host "📝 Configurando tarea programada (MODO VENTANA)..." -ForegroundColor Yellow

$action = New-ScheduledTaskAction `
    -Execute $pythonPath `
    -Argument "`"$scriptPath`"" `
    -WorkingDirectory $projectPath

# Codigo para ejecutar al iniciar sesión (con ventana)

# $trigger = New-ScheduledTaskTrigger -AtLogOn -User $userName

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
# se quito esto del Register-ScheduledTask para evitar que se ejecute al iniciar sesión
# -Trigger $trigger `

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Principal $principal `
    -Settings $settings `
    -Description "Scanner Connector API With Console - Ventana visible con logs protegidos (no se puede cerrar con X)" `
    -Force | Out-Null

Write-Host "✅ Tarea programada registrada (MODO VENTANA VISIBLE)" -ForegroundColor Green

# Iniciar tarea
Write-Host "`n🚀 Iniciando servicio con ventana de consola..." -ForegroundColor Yellow
Write-Host "   ⚠️  Se abrirá una ventana de consola que NO se puede cerrar" -ForegroundColor Yellow
Write-Host "   ⚠️  Para detener: Stop-ScheduledTask -TaskName `"$taskName`"" -ForegroundColor Yellow

Start-ScheduledTask -TaskName $taskName
Start-Sleep -Seconds 5

# Verificar proceso
$proc = Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle -like "*Scanner*" }
if ($proc) {
    Write-Host "✅ Proceso python corriendo con ventana visible (PID: $($proc.Id))" -ForegroundColor Green
} else {
    $anyPython = Get-Process python -ErrorAction SilentlyContinue
    if ($anyPython) {
        Write-Host "⚠️  Proceso python detectado, verificando ventana..." -ForegroundColor Yellow
    } else {
        Write-Host "⚠️  Proceso no detectado inmediatamente" -ForegroundColor Yellow
    }
}

# Probar endpoint
Write-Host "`n🔍 Probando conexión con la API..." -ForegroundColor Yellow
Start-Sleep -Seconds 3

try {
    $response = Invoke-WebRequest -Uri "http://localhost:5000/api/scan/health" -UseBasicParsing -TimeoutSec 10
    $content = $response.Content | ConvertFrom-Json
    Write-Host "✅ API respondiendo correctamente" -ForegroundColor Green
    Write-Host "   Status: $($content.status)" -ForegroundColor White
} catch {
    Write-Host "⚠️  API aún no responde. Puede tardar unos segundos más." -ForegroundColor Yellow
    Write-Host "   Verifica la ventana de consola que se abrió." -ForegroundColor Yellow
}

# Resumen final
Write-Host "`n════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  INSTALACIÓN COMPLETADA (MODO VENTANA PROTEGIDA)" -ForegroundColor Green
Write-Host "════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "`n✅ Se abrió una ventana de consola con logs en tiempo real" -ForegroundColor Green
Write-Host "✅ La ventana está PROTEGIDA contra cierre accidental:" -ForegroundColor Green
Write-Host "   • Botón X deshabilitado" -ForegroundColor Gray
Write-Host "   • Alt+F4 bloqueado" -ForegroundColor Gray
Write-Host "   • Ctrl+C permitido (para cerrar el servidor)" -ForegroundColor Green
Write-Host "`n📋 Comandos útiles:" -ForegroundColor White
Write-Host "   • Ver estado:    Get-ScheduledTask -TaskName `"$taskName`"" -ForegroundColor Gray
Write-Host "   • DETENER:       Stop-ScheduledTask -TaskName `"$taskName`"" -ForegroundColor Yellow
Write-Host "   • Iniciar:       Start-ScheduledTask -TaskName `"$taskName`"" -ForegroundColor Gray
Write-Host "   • Ver logs:      Get-Content `"$projectPath\logs\api_production.log`" -Tail 50" -ForegroundColor Gray
Write-Host "   • Probar API:    curl http://localhost:5000/api/scan/health" -ForegroundColor Gray
Write-Host "`n⚠️  IMPORTANTE:" -ForegroundColor Yellow
Write-Host "   La ventana de consola NO se puede cerrar normalmente." -ForegroundColor Yellow
Write-Host "   Esto es INTENCIONAL para evitar cierres accidentales." -ForegroundColor Yellow
Write-Host "   Para detener el servidor, ejecute como Admin:" -ForegroundColor Yellow
Write-Host "   Stop-ScheduledTask -TaskName `"$taskName`"" -ForegroundColor Cyan
Write-Host ""
pause
