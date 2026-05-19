# iniciar_servidor.ps1
# Script simple para INICIAR el servidor Scanner Connector API
# Ejecutar como Administrador: .\iniciar_servidor.ps1
# ============================================================================

# Verificar que se ejecuta como Administrador
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "`n ERROR: Este script debe ejecutarse como Administrador" -ForegroundColor Red
    Write-Host "   Haz clic derecho en el acceso directo y ejecuta como administrador" -ForegroundColor Yellow
    pause
    exit 1
}

# Configuracion
$taskName = "tarea conector con ventana"
$projectPath = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "`n" -NoNewline
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  INICIAR SCANNER CONNECTOR API" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# Verificar si la tarea programada existe
Write-Host "`nVerificando tarea programada..." -ForegroundColor Yellow
$task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue

if (-not $task) {
    Write-Host "ERROR: La tarea programada NO existe" -ForegroundColor Red
    Write-Host "`n   Primero debes ejecutar el instalador:" -ForegroundColor Yellow
    Write-Host "   .\instalar_tarea_con_ventana.ps1" -ForegroundColor Cyan
    Write-Host ""
    pause
    exit 1
}

Write-Host "OK: Tarea programada encontrada" -ForegroundColor Green

# Verificar si ya esta corriendo
Write-Host "`nVerificando estado del servidor..." -ForegroundColor Yellow
$taskInfo = Get-ScheduledTaskInfo -TaskName $taskName
$isRunning = $taskInfo.LastTaskResult -eq 267009 -or (Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle -like "*Scanner*" })

if ($isRunning) {
    Write-Host "AVISO: El servidor YA esta corriendo" -ForegroundColor Yellow
    
    # Intentar verificar API
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:5000/api/scan/health" -UseBasicParsing -TimeoutSec 3 -ErrorAction SilentlyContinue
        if ($response.StatusCode -eq 200) {
            Write-Host "OK: API respondiendo en http://localhost:5000" -ForegroundColor Green
        }
    } catch {
        Write-Host "AVISO: Proceso detectado pero API no responde aun" -ForegroundColor Yellow
    }
    
    Write-Host "`nPara detener el servidor:" -ForegroundColor White
    Write-Host "   Stop-ScheduledTask -TaskName '$taskName' o tambien Presionar Ctrl + c sobre la terminal" -ForegroundColor Cyan
    Write-Host ""
    pause
    exit 0
}

# Iniciar servidor
Write-Host "Iniciando servidor..." -ForegroundColor Green
Write-Host "   Se abrira una ventana con logs en tiempo real" -ForegroundColor Gray

Start-ScheduledTask -TaskName $taskName
Start-Sleep -Seconds 3

# Verificar que inicio
$proc = Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle -like "*Scanner*" }
if ($proc) {
    Write-Host "OK: Servidor iniciado correctamente (PID: $($proc.Id))" -ForegroundColor Green
} else {
    Write-Host "AVISO: Iniciando... Verifica la ventana que se abrio" -ForegroundColor Yellow
}

# Probar API
Write-Host "`nProbando conexion con la API..." -ForegroundColor Yellow
Start-Sleep -Seconds 4

try {
    $response = Invoke-WebRequest -Uri "http://localhost:5000/api/scan/health" -UseBasicParsing -TimeoutSec 10
    $content = $response.Content | ConvertFrom-Json
    Write-Host "OK: API respondiendo correctamente" -ForegroundColor Green
    Write-Host "   Status: $($content.status)" -ForegroundColor White
    Write-Host "   URL: http://localhost:5000" -ForegroundColor Cyan
} catch {
    Write-Host "AVISO: API aun no responde. Puede tardar unos segundos mas." -ForegroundColor Yellow
    Write-Host "   Verifica la ventana de consola que se abrio." -ForegroundColor Yellow
}

# Resumen
Write-Host "`n============================================================" -ForegroundColor Cyan
Write-Host "  SERVIDOR INICIADO" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "`nLogs en tiempo real: Ventana de consola abierta" -ForegroundColor White
Write-Host "Logs en archivo: $projectPath\logs\api_production.log" -ForegroundColor Gray
Write-Host "`nPara DETENER el servidor (desde PowerShell Admin):" -ForegroundColor Yellow
Write-Host "   Stop-ScheduledTask -TaskName '$taskName' o tambien Presionar Ctrl + c sobre la terminal" -ForegroundColor Cyan
Write-Host ""
pause
