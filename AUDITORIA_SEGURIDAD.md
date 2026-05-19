# Auditoria de Seguridad - Estado Actual

Este documento describe el comportamiento real actual de la auditoria de seguridad en este proyecto.

## 1. Objetivo

Detectar vulnerabilidades de dependencias Python con `pip-audit` sin romper la operacion productiva del conector TWAIN.

## 2. Auditoria local (equipo Windows)

La auditoria local se ejecuta con:

- Script: `scripts/security_audit_auto.py`
- Tarea instalada por: `instalar_tarea_auditoria.ps1`
- Nombre de tarea: `tarea auditoria`
- Frecuencia: semanal, martes a las 9:00 AM

### 2.1 Comportamiento real

La auditoria local:

1. Ejecuta `pip-audit`.
2. Detecta y lista paquetes vulnerables.
3. NO actualiza dependencias automaticamente.
4. Consolida resultados en `logs/cleanup_audit.txt`.
5. Reinicia ese reporte cuando supera 30 dias de antiguedad.

Esto se hace para reducir riesgo operativo en produccion (ejemplo: evitar romper compatibilidad TWAIN por una actualizacion automatica).

## 3. Instalacion y uso local

### Instalar tarea (PowerShell como Administrador)

```powershell
.\instalar_tarea_auditoria.ps1
```

### Ver estado

```powershell
Get-ScheduledTask -TaskName "tarea auditoria"
```

### Ejecutar auditoria manual

```powershell
Start-ScheduledTask -TaskName "tarea auditoria"
```

### Ver reporte consolidado

```powershell
Get-Content logs\cleanup_audit.txt -Tail 120
revisar el archivo completo dentro de la carpeta logs para ver el historial completo de auditorias.
```

## 4. Logs y evidencias

Archivos relevantes:

- `logs/cleanup_audit.txt`: reporte consolidado mensual de auditoria.
- `logs/api_production.log`: logs de la API (no es el reporte de auditoria).

Nota: actualmente el flujo local no genera `logs/security_audit.log` como archivo principal de auditoria.

## 5. Diferencia con GitHub Actions

En CI (GitHub Actions) existe un workflow separado:

- Archivo: `.github/workflows/security-audit.yml`

Ese flujo puede actualizar dependencias y crear PR automaticamente cuando se detectan vulnerabilidades. No esta en uso ya que se prioriza la estabilidad operativa en produccion, pero es una opcion para el futuro.

Resumen:

- Local (Windows, tarea programada): solo audita y reporta.
- GitHub Actions: puede auditar y proponer actualizaciones automaticas por PR.

## 6. Recomendacion operativa

Cuando el reporte local detecte vulnerabilidades:

1. Revisar impacto del paquete vulnerable.
2. Probar actualizacion en entorno de pruebas.
3. Validar escaneo TWAIN y endpoints criticos.
4. Aplicar en produccion solo despues de validacion.

## 7. Comandos utiles

```powershell
# Estado de tarea
Get-ScheduledTask -TaskName "tarea auditoria"

# Info de ultima ejecucion
Get-ScheduledTaskInfo -TaskName "tarea auditoria"

# Ejecutar ahora
Start-ScheduledTask -TaskName "tarea auditoria"

# Ver reporte
Get-Content logs\cleanup_audit.txt -Tail 120

# Desinstalar tarea
Unregister-ScheduledTask -TaskName "tarea auditoria" -Confirm:$false
```
