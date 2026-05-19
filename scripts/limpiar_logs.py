"""
Script de limpieza automática de logs.
Ejecutado semanalmente por Tarea Programada (Martes 10:00 AM).

Estrategia actual:
1. LOGS OPERATIVOS (.log):
    - Se eliminan semanalmente para evitar acumulación

2. REPORTE DE AUDITORÍA CONSOLIDADO (cleanup_audit.txt):
    - NO se elimina en la limpieza semanal
    - Su retención mensual (30 días) la gestiona security_audit_auto.py

3. RESUMEN DE LIMPIEZA:
    - Se genera un resumen por ejecución (resumen_limpieza_*.log)
    - El resumen previo se elimina en la siguiente ejecución
"""

import sys
import shutil
from pathlib import Path
from datetime import datetime, timedelta


PROJECT_ROOT = Path(__file__).parent.parent
LOG_DIR = PROJECT_ROOT / 'logs'
LOG_DIR.mkdir(exist_ok=True)

# Configuración de limpieza
CLEANUP_SUMMARY_PREFIX = "resumen_limpieza_"
MONTHLY_AUDIT_FILE = "cleanup_audit.txt"
LEGACY_AUDIT_CACHE_DIRS = ["pip_audit_cache", "pip_audit_cache_run"]

def get_file_size_mb(file_path):
    """Obtiene el tamaño del archivo en MB."""
    try:
        return file_path.stat().st_size / (1024 * 1024)
    except Exception:
        return 0


def get_file_age_days(file_path):
    """Calcula la edad del archivo en días."""
    try:
        mtime = file_path.stat().st_mtime
        file_date = datetime.fromtimestamp(mtime)
        return (datetime.now() - file_date).days
    except Exception:
        return 0


def clean_logs():
    """
    Estrategia semanal de limpieza:
    1. Elimina logs operativos (.log)
    2. Conserva cleanup_audit.txt (reporte mensual de auditoría)
    3. Genera resumen de limpieza y elimina el resumen anterior
    """
    now = datetime.now()
    summary_lines = []

    summary_lines.append("=" * 70)
    summary_lines.append("LIMPIEZA SEMANAL DE LOGS - Scanner Connector API")
    summary_lines.append(f"Fecha de ejecución: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    summary_lines.append("=" * 70)
    summary_lines.append(f"Directorio: {LOG_DIR}")
    summary_lines.append("Estrategia: Eliminar logs operativos semanalmente")
    summary_lines.append("")

    # Verificar que existe el directorio
    if not LOG_DIR.exists():
        summary_lines.append("El directorio de logs no existe. No hay nada que limpiar.")
        _write_report(summary_lines, now)
        print("No hay directorio de logs.")
        return 0

    # 1. Obtener logs operativos a eliminar
    logs_to_delete = sorted(
        [
            f for f in LOG_DIR.glob('*.log')
            if f.is_file() and not f.name.startswith(CLEANUP_SUMMARY_PREFIX)
        ],
        key=lambda f: f.name
    )

    summary_lines.append("-" * 70)
    summary_lines.append("DETALLE DE ARCHIVOS ANTES DE BORRAR")
    summary_lines.append("-" * 70)

    total_size = 0
    if logs_to_delete:
        for log_file in logs_to_delete:
            size_mb = get_file_size_mb(log_file)
            age_days = get_file_age_days(log_file)
            total_size += log_file.stat().st_size
            summary_lines.append(f"  {log_file.name:<44} {size_mb:>8.2f} MB | {age_days:>4} días")
    else:
        summary_lines.append("No se encontraron logs operativos para eliminar")

    summary_lines.append(f"\nEspacio total ocupado: {total_size / (1024 * 1024):.2f} MB")

    # 2. Eliminar logs operativos
    summary_lines.append("")
    summary_lines.append("-" * 70)
    summary_lines.append("RESULTADO DE ELIMINACIÓN")
    summary_lines.append("-" * 70)

    deleted_count = 0
    space_freed = 0
    error_count = 0

    for log_file in logs_to_delete:
        try:
            file_size = log_file.stat().st_size
            log_file.unlink()
            space_freed += file_size
            deleted_count += 1
            summary_lines.append(f"  [OK]    {log_file.name}")
        except Exception as e:
            error_count += 1
            summary_lines.append(f"  [ERROR] {log_file.name}: {e}")

    if not logs_to_delete:
        summary_lines.append("  [INFO]  No hubo archivos para borrar")

    # 2b. Eliminar caches heredados de auditoría en logs
    summary_lines.append("")
    summary_lines.append("-" * 70)
    summary_lines.append("LIMPIEZA DE CACHES DE AUDITORÍA (LEGACY)")
    summary_lines.append("-" * 70)

    removed_cache_dirs = 0
    for dir_name in LEGACY_AUDIT_CACHE_DIRS:
        cache_dir = LOG_DIR / dir_name
        if not cache_dir.exists():
            summary_lines.append(f"  [INFO]  {dir_name} no existe")
            continue

        try:
            shutil.rmtree(cache_dir)
            removed_cache_dirs += 1
            summary_lines.append(f"  [OK]    {dir_name} eliminado")
        except Exception as e:
            error_count += 1
            summary_lines.append(f"  [ERROR] {dir_name}: {e}")

    # 3. Mostrar estado de cleanup_audit.txt
    summary_lines.append("")
    summary_lines.append("-" * 70)
    summary_lines.append("REPORTE MENSUAL DE AUDITORÍA")
    summary_lines.append("-" * 70)

    monthly_audit = LOG_DIR / MONTHLY_AUDIT_FILE
    if monthly_audit.exists():
        size_kb = monthly_audit.stat().st_size / 1024
        age_days = get_file_age_days(monthly_audit)
        summary_lines.append(f"  • {monthly_audit.name} ({age_days} días, {size_kb:.1f} KB)")
        summary_lines.append("  ✅ Se conserva; su rotación mensual la gestiona security_audit_auto.py")
    else:
        summary_lines.append("  [INFO] cleanup_audit.txt aún no existe")

    # 4. Resumen final
    summary_lines.append("")
    summary_lines.append("=" * 70)
    summary_lines.append("RESUMEN")
    summary_lines.append("=" * 70)
    summary_lines.append(f"Archivos eliminados: {deleted_count} de {len(logs_to_delete)}")
    summary_lines.append(f"Caches removidos:    {removed_cache_dirs} de {len(LEGACY_AUDIT_CACHE_DIRS)}")
    summary_lines.append(f"Espacio liberado:    {space_freed / (1024 * 1024):.2f} MB")
    summary_lines.append(f"Errores:             {error_count}")
    summary_lines.append("")

    # Próxima limpieza
    days_ahead = 1 - now.weekday()  # 1 = martes
    if days_ahead <= 0:
        days_ahead += 7
    next_cleanup = now + timedelta(days=days_ahead)

    summary_lines.append(f"Próxima limpieza programada: {next_cleanup.strftime('%A %d de %B de %Y')} a las 10:00 AM")
    summary_lines.append("Este archivo de resumen se eliminará en la próxima limpieza.")
    summary_lines.append("=" * 70)

    # Escribir reporte
    _write_report(summary_lines, now)

    # Imprimir en consola
    for line in summary_lines:
        print(line)

    return deleted_count


def _write_report(lines, now):
    """
    Escribe un resumen de limpieza con timestamp.
    El resumen previo se elimina en la próxima ejecución.
    """
    old_summaries = sorted(
        [f for f in LOG_DIR.glob(f'{CLEANUP_SUMMARY_PREFIX}*.log') if f.is_file()],
        key=lambda f: f.stat().st_mtime
    )

    for old_summary in old_summaries:
        try:
            old_summary.unlink()
        except Exception as e:
            print(f"WARN: No se pudo eliminar resumen anterior {old_summary.name}: {e}")

    report_file = LOG_DIR / f'{CLEANUP_SUMMARY_PREFIX}{now.strftime("%Y%m%d_%H%M%S")}.log'
    try:
        report_file.write_text('\n'.join(lines), encoding='utf-8')
        print(f"\nResumen de limpieza guardado: {report_file.name}")
    except Exception as e:
        print(f"ERROR: No se pudo escribir el reporte: {e}")


def main():
    """Función principal."""
    try:
        start_time = datetime.now()
        print(f"Inicio: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")

        deleted_count = clean_logs()

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        print(f"\nDuración: {duration:.2f} segundos")
        print(f"Fin: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")

        return 0

    except Exception as e:
        print(f"ERROR FATAL: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
