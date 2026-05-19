# instalar_tarea_auditoria.ps1
# Instalador de Tarea Programada para Auditoría de Seguridad
# Ejecutar como Administrador: .\instalar_tarea_auditoria.ps1
# ============================================================================

# Verificar permisos de Administrador
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "`n❌ Ejecutar como Administrador" -ForegroundColor Red
    pause
    exit 1
}

# Configuración
$taskName = "tarea auditoria"
$projectPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonPath = Join-Path $projectPath "venv\Scripts\python.exe" # pythonw si se prefiere sin ventana
$scriptPath = Join-Path $projectPath "scripts\security_audit_auto.py"
$currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name

Write-Host "`n============================================================" -ForegroundColor Cyan
Write-Host "  Instalador - Auditoría de Seguridad Automática" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# Verificar archivos
if (-not (Test-Path $pythonPath)) {
    Write-Host "`n❌ python.exe no encontrado: $pythonPath" -ForegroundColor Red
    Write-Host "   Verifica que el entorno virtual esté creado correctamente." -ForegroundColor Yellow
    pause
    exit 1
}

if (-not (Test-Path $scriptPath)) {
    Write-Host "`n❌ Script no encontrado: $scriptPath" -ForegroundColor Red
    pause
    exit 1
}

Write-Host "✅ Archivos verificados" -ForegroundColor Green

# Eliminar tarea anterior
Write-Host "`n🔄 Limpiando tarea anterior..." -ForegroundColor Yellow
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

# Crear tarea programada
Write-Host "📝 Configurando tarea..." -ForegroundColor Yellow

$action = New-ScheduledTaskAction -Execute $pythonPath -Argument "`"$scriptPath`"" -WorkingDirectory $projectPath

# Ejecutar cada martes a las 9:00 AM
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Tuesday -At 9am

$principal = New-ScheduledTaskPrincipal -UserId $currentUser -LogonType Interactive -RunLevel Highest

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 5) `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1)

# Registrar tarea
Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Description "Auditoría de seguridad automática - Cada martes 9:00 AM (reporte mensual cleanup_audit.txt)" `
    -Force | Out-Null

Write-Host "✅ Tarea programada instalada" -ForegroundColor Green
Write-Host "`n📅 Programación: Cada martes a las 9:00 AM" -ForegroundColor White
Write-Host "� Modo: Solo auditoría (NO actualización automática)" -ForegroundColor White
Write-Host "⚠️  Acción requerida: Revisar logs si hay vulnerabilidades" -ForegroundColor Yellow
Write-Host "🔄 Auto-reinicio: 3 intentos cada 5 minutos si falla" -ForegroundColor White
Write-Host "🖥️  Ejecución: Silenciosa en segundo plano (sin ventana)" -ForegroundColor White
Write-Host "📝 Reporte mensual: $projectPath\logs\cleanup_audit.txt" -ForegroundColor Gray
Write-Host "`n📋 Detalles de seguridad:" -ForegroundColor White
Write-Host "  • Audita vulnerabilidades semanalmente" -ForegroundColor Gray
Write-Host "  • Consolida resultados en cleanup_audit.txt" -ForegroundColor Gray
Write-Host "  • Reinicia el reporte cada 30 días desde su creación" -ForegroundColor Gray
Write-Host "  • NO actualiza dependencias automáticamente" -ForegroundColor Gray
Write-Host "  • Requiere revisión manual antes de actualizar en producción" -ForegroundColor Gray
Write-Host "`n✅ Ventajas de esta estrategia:" -ForegroundColor Green
Write-Host "  • Evita romper dependencias críticas (TWAIN)" -ForegroundColor Gray
Write-Host "  • Permite testing antes de actualizar" -ForegroundColor Gray
Write-Host "  • Mantiene control manual sobre cambios en producción" -ForegroundColor Gray
Write-Host "`nComandos útiles:" -ForegroundColor White
Write-Host "  • Ver estado: Get-ScheduledTask -TaskName `"$taskName`"" -ForegroundColor Gray
Write-Host "  • Ejecutar ahora: Start-ScheduledTask -TaskName `"$taskName`"" -ForegroundColor Gray
Write-Host "  • Ver reporte: Get-Content logs\cleanup_audit.txt -Tail 80" -ForegroundColor Gray
Write-Host "`n⚠️  IMPORTANTE: Revisa los logs regularmente para vulnerabilidades reportadas." -ForegroundColor Yellow
Write-Host "   Si encuentras vulnerabilidades, evalúa actualizar en ambiente de prueba primero." -ForegroundColor Yellow
Write-Host ""
pause
