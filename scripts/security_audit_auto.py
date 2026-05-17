#!/usr/bin/env python
# scripts/security_audit_auto.py
"""
Auditoría de seguridad automática.
- Audita vulnerabilidades con pip-audit semanalmente
- Acumula resultados en un único reporte cleanup_audit.txt
- Reinicia el reporte automáticamente cuando cumple 30 días
- SOLO reporta vulnerabilidades (no actualiza automáticamente por seguridad)
"""

import subprocess
import sys
import json
import time
import re
import tempfile
import threading
import queue
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
REQUIREMENTS_FILE = PROJECT_ROOT / "requirements.txt"
LOG_DIR = PROJECT_ROOT / "logs"
AUDIT_REPORT = LOG_DIR / "cleanup_audit.txt"
RETENTION_DAYS = 30

LOG_DIR.mkdir(exist_ok=True)


def log(message):
    """Registra mensaje en consola."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] {message}"
    print(log_entry)


def _report_age_days(file_path):
    """Retorna la edad del archivo en días."""
    try:
        return (datetime.now() - datetime.fromtimestamp(file_path.stat().st_mtime)).days
    except Exception:
        return 0


def _reset_report_if_expired():
    """Reinicia el reporte mensual si superó la retención de 30 días."""
    if not AUDIT_REPORT.exists():
        return

    if _report_age_days(AUDIT_REPORT) < RETENTION_DAYS:
        return

    try:
        AUDIT_REPORT.unlink()
        log(f"🧹 Reporte mensual reiniciado (>{RETENTION_DAYS} días): {AUDIT_REPORT.name}")
    except Exception as e:
        log(f"⚠️ No se pudo reiniciar reporte mensual: {e}")


def _append_monthly_audit(run_lines):
    """Agrega resultado semanal al reporte mensual consolidado."""
    _reset_report_if_expired()

    if not AUDIT_REPORT.exists():
        header = [
            "=" * 70,
            "REPORTE CONSOLIDADO DE AUDITORÍA DE DEPENDENCIAS",
            f"Creado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"Retención: {RETENTION_DAYS} días desde creación",
            "=" * 70,
            ""
        ]
        AUDIT_REPORT.write_text("\n".join(header), encoding="utf-8")

    with open(AUDIT_REPORT, "a", encoding="utf-8") as f:
        f.write("\n".join(run_lines) + "\n\n")


def run(cmd, show_progress=False, heartbeat_seconds=8, echo_stdout=True, echo_stderr=True):
    """Ejecuta comando con salida en vivo y retorna stdout/stderr separados."""
    process = None
    stdout_lines = []
    stderr_lines = []
    last_output = time.monotonic()
    line_queue = queue.Queue()

    def _enqueue_output(pipe, out_queue, stream_name):
        """Lee stdout en segundo plano para evitar bloqueos en readline()."""
        try:
            for line in iter(pipe.readline, ""):
                out_queue.put((stream_name, line))
        finally:
            pipe.close()

    try:
        process = subprocess.Popen(
            cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=PROJECT_ROOT,
            bufsize=1,
        )

        stdout_reader = threading.Thread(
            target=_enqueue_output,
            args=(process.stdout, line_queue, "stdout"),
            daemon=True,
        )
        stderr_reader = threading.Thread(
            target=_enqueue_output,
            args=(process.stderr, line_queue, "stderr"),
            daemon=True,
        )
        stdout_reader.start()
        stderr_reader.start()

        while True:
            try:
                stream_name, line = line_queue.get(timeout=0.2)
                last_output = time.monotonic()

                if stream_name == "stdout":
                    stdout_lines.append(line)
                    if echo_stdout:
                        print(line.rstrip())
                else:
                    stderr_lines.append(line)
                    if echo_stderr:
                        print(line.rstrip(), file=sys.stderr)
                continue
            except queue.Empty:
                if process.poll() is not None:
                    break

                if show_progress and (time.monotonic() - last_output) >= heartbeat_seconds:
                    log("⏳ Auditoría en curso... esperando respuesta del servicio de vulnerabilidades")
                    last_output = time.monotonic()

        # Drenar remanente en cola
        while not line_queue.empty():
            stream_name, rem_line = line_queue.get_nowait()
            if stream_name == "stdout":
                stdout_lines.append(rem_line)
                if echo_stdout:
                    print(rem_line.rstrip())
            else:
                stderr_lines.append(rem_line)
                if echo_stderr:
                    print(rem_line.rstrip(), file=sys.stderr)

        stdout_reader.join(timeout=1)
        stderr_reader.join(timeout=1)

        return subprocess.CompletedProcess(
            args=cmd,
            returncode=process.returncode,
            stdout="".join(stdout_lines),
            stderr="".join(stderr_lines),
        )
    except KeyboardInterrupt:
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        raise


def _extract_vulnerable_packages_from_text(text):
    """Extrae posibles paquetes vulnerables desde salida de texto/tablas."""
    vulnerable_packages = set()
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or "Name" in line or "Found" in line:
            continue

        if "┃" in line:
            parts = [p.strip() for p in line.split("┃") if p.strip()]
            if parts:
                vulnerable_packages.add(parts[0])
            continue

        match = re.match(r"^([A-Za-z0-9_.-]+)\s+\S+\s+(GHSA|PYSEC|CVE)-", line)
        if match:
            vulnerable_packages.add(match.group(1))

    return list(vulnerable_packages)


def _extract_json_payload(text):
    """Extrae un bloque JSON válido desde texto con ruido alrededor."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    return text[start:end + 1]


def _count_requirements_lines():
    """Cuenta dependencias no vacías/no comentario en requirements.txt."""
    try:
        lines = REQUIREMENTS_FILE.read_text(encoding="utf-8").splitlines()
        return sum(1 for line in lines if line.strip() and not line.strip().startswith("#"))
    except Exception:
        return None


def ensure_pip_audit():
    """Instala pip-audit si no está disponible."""
    try:
        subprocess.run([sys.executable, "-m", "pip", "show", "pip-audit"], 
                      capture_output=True, check=True)
    except subprocess.CalledProcessError:
        log("📦 Instalando pip-audit...")
        install_result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "pip-audit"],
            capture_output=True,
            text=True,
        )
        if install_result.returncode != 0:
            raise RuntimeError(
                "No se pudo instalar pip-audit. "
                f"Detalle: {(install_result.stderr or install_result.stdout or '').strip()}"
            )


def get_vulnerable_packages():
    """Ejecuta auditoría y retorna flujo, paquetes vulnerables y detalle."""
    # Evita carpetas persistentes en el proyecto: usa cache temporal por ejecución.
    with tempfile.TemporaryDirectory(prefix="pip_audit_") as temp_cache_dir:
        result = run(
            f'"{sys.executable}" -m pip_audit -r "{REQUIREMENTS_FILE}" --format json --progress-spinner off --cache-dir "{temp_cache_dir}"',
            show_progress=True,
            echo_stdout=False,
            echo_stderr=True,
        )
    
    if result.returncode == 0:
        log("✅ No se encontraron vulnerabilidades en pip-audit")
        return {
            "status": "sin_vulnerabilidades",
            "packages": [],
            "detail": "pip-audit retornó 0",
        }
    
    vulnerable_packages = set()
    raw_output = result.stdout.strip()
    combined_output = "\n".join(
        part for part in [result.stdout.strip(), result.stderr.strip()] if part
    )
    stderr_tail = (result.stderr or "").strip().splitlines()[-1:] or [""]
    stderr_last = stderr_tail[0]

    try:
        data = json.loads(raw_output)
        if "dependencies" in data:
            for dep in data["dependencies"]:
                if dep.get("vulns"):
                    pkg_name = dep["name"]
                    vulnerable_packages.add(pkg_name)
                    # Log detalles de vulnerabilidades
                    for vuln in dep["vulns"]:
                        vuln_id = vuln.get("id", "N/A")
                        vuln_desc = vuln.get("description", "Sin descripción")[:80]
                        log(f"  • {pkg_name}: {vuln_id} - {vuln_desc}...")

        vulnerable_list = list(vulnerable_packages)
        if vulnerable_list:
            return {
                "status": "vulnerabilidades_encontradas",
                "packages": vulnerable_list,
                "detail": "Resultado JSON parseado correctamente",
            }

        return {
            "status": "auditoria_indeterminada",
            "packages": [],
            "detail": f"pip-audit retornó error ({result.returncode}) y JSON no incluyó vulnerabilidades",
        }
    except json.JSONDecodeError:
        json_payload = _extract_json_payload(raw_output)
        if json_payload:
            try:
                data = json.loads(json_payload)
                if "dependencies" in data:
                    for dep in data["dependencies"]:
                        if dep.get("vulns"):
                            vulnerable_packages.add(dep["name"])

                vulnerable_list = list(vulnerable_packages)
                if vulnerable_list:
                    return {
                        "status": "vulnerabilidades_encontradas",
                        "packages": vulnerable_list,
                        "detail": "JSON recuperado desde salida con ruido",
                    }
            except json.JSONDecodeError:
                pass

        log("⚠️ No se pudo parsear JSON de pip-audit. Se intentará extraer desde la salida textual (sin re-ejecutar).")
        for pkg in _extract_vulnerable_packages_from_text(combined_output):
            vulnerable_packages.add(pkg)

    vulnerable_list = list(vulnerable_packages)
    if vulnerable_list:
        return {
            "status": "vulnerabilidades_encontradas",
            "packages": vulnerable_list,
            "detail": "Parseo JSON falló; extracción textual exitosa",
        }

    return {
        "status": "auditoria_indeterminada",
        "packages": [],
        "detail": (
            f"Parseo JSON falló con retorno {result.returncode} y no se pudieron extraer vulnerabilidades de texto"
            + (f". Último stderr: {stderr_last}" if stderr_last else "")
        ),
    }


def main():
    """Ejecuta auditoría y actualiza solo paquetes vulnerables."""
    run_summary = []
    start_ts = time.monotonic()
    dep_count = _count_requirements_lines()

    log("🔒 AUDITORÍA DE SEGURIDAD")
    log(f"Proyecto: {PROJECT_ROOT}")
    if dep_count is not None:
        log(f"Dependencias a auditar: {dep_count}")
    log("Tip: puedes cancelar con Ctrl + C")
    run_summary.append("-" * 70)
    run_summary.append(f"Ejecución: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    run_summary.append("-" * 70)
    
    # 1. Instalar pip-audit si no existe
    ensure_pip_audit()
    
    # 2. Obtener paquetes vulnerables
    log("🔍 Auditando vulnerabilidades...")
    audit_result = get_vulnerable_packages()
    audit_status = audit_result["status"]
    vulnerable = audit_result["packages"]
    audit_detail = audit_result["detail"]

    run_summary.append(f"Flujo de auditoría: {audit_status}")
    run_summary.append(f"Detalle: {audit_detail}")
    log(f"🧭 Flujo detectado: {audit_status}")
    
    if audit_status == "auditoria_indeterminada":
        log("❌ AUDITORÍA INDETERMINADA")
        log("   No se pudo confirmar si existen vulnerabilidades.")
        log("   Revisar conectividad/red o salida completa de pip-audit.")
        run_summary.append("Estado: AUDITORIA_INDETERMINADA")
        _append_monthly_audit(run_summary)
        log("=" * 60)
        elapsed = time.monotonic() - start_ts
        log(f"⏱️ Duración total: {elapsed:.1f} segundos")
        return 2

    if vulnerable:
        log(f"⚠️ ALERTA: Encontradas vulnerabilidades en {len(vulnerable)} paquetes:")
        run_summary.append(f"Estado: VULNERABILIDADES ENCONTRADAS ({len(vulnerable)})")
        run_summary.append("Dependencias que requieren revisión/actualización:")
        for pkg in vulnerable:
            log(f"  - {pkg}")
            run_summary.append(f"  - {pkg}")
        
        log("")
        log("📌 ACCIÓN REQUERIDA: Revisar manualmente y actualizar")
        log("   Cambios: Solo auditoría. NO se actualizarán automáticamente.")
        log("")
        
        # ===== BLOQUE DE ACTUALIZACIÓN AUTOMÁTICA - COMENTADO POR SEGURIDAD =====
        # MOTIVO: Actualizar automáticamente en producción puede romper dependencias
        # delicadas (como TWAIN) y dejar el servicio sin API disponible.
        # 
        # Para actualizar manualmente:
        # 1. Revisar los paquetes vulnerables listados arriba
        # 2. Hacer testing en ambiente local primero
        # 3. Si OK, ejecutar: pip install --upgrade <paquete>
        # 4. Actualizar requirements.txt: pip freeze > requirements.txt
        # 5. Verificar que todo funciona después del cambio
        # 
        # # 3. Actualizar SOLO los paquetes vulnerables
        # log("📦 Actualizando paquetes vulnerables automáticamente...")
        # updated_count = 0
        # failed_updates = []
        # 
        # for pkg in vulnerable:
        #     log(f"  🔄 Actualizando {pkg}...")
        #     update_result = run(f'"{sys.executable}" -m pip install --upgrade "{pkg}"')
        #     
        #     if update_result.returncode == 0:
        #         log(f"  ✅ {pkg} actualizado exitosamente")
        #         updated_count += 1
        #     else:
        #         log(f"  ❌ Error actualizando {pkg}")
        #         failed_updates.append(pkg)
        # 
        # log(f"📊 Actualizados: {updated_count}/{len(vulnerable)} paquetes")
        # 
        # if failed_updates:
        #     log(f"⚠️ Fallos en: {', '.join(failed_updates)}")
        # 
        # # 4. Regenerar requirements.txt
        # log("📝 Actualizando requirements.txt...")
        # freeze_result = run(f'"{sys.executable}" -m pip freeze')
        # if freeze_result.returncode == 0:
        #     with open(REQUIREMENTS_FILE, "w", encoding="utf-8") as f:
        #         f.write(freeze_result.stdout)
        #     log("✅ requirements.txt actualizado")
        # 
        # # 5. Re-auditar para verificar
        # log("🔄 Re-auditando para verificar correcciones...")
        # result = run(f'"{sys.executable}" -m pip_audit -r "{REQUIREMENTS_FILE}"')
        # 
        # if result.returncode == 0:
        #     log("✅ TODAS las vulnerabilidades fueron resueltas")
        #     return 0
        # else:
        #     log("⚠️ Aún quedan algunas vulnerabilidades (pueden requerir actualización manual)")
        #     # Mostrar resumen de vulnerabilidades restantes
        #     remaining = get_vulnerable_packages()
        #     if remaining:
        #         log(f"📋 Vulnerabilidades restantes en: {', '.join(remaining)}")
        # ===== FIN BLOQUE COMENTADO =====
        
        log("")
        log(f"📋 Reporte consolidado: logs/{AUDIT_REPORT.name}")
        log("="*60)
        elapsed = time.monotonic() - start_ts
        log(f"⏱️ Duración total: {elapsed:.1f} segundos")
        _append_monthly_audit(run_summary)
        return 1
    else:
        log("✅ Sin vulnerabilidades")
        run_summary.append("Estado: Sin vulnerabilidades detectadas")
        _append_monthly_audit(run_summary)
        log("=" * 60)
        elapsed = time.monotonic() - start_ts
        log(f"⏱️ Duración total: {elapsed:.1f} segundos")
        return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        log("⛔ Auditoría cancelada por usuario (Ctrl + C)")
        sys.exit(130)
    except Exception as e:
        log(f"❌ Error: {e}")
        sys.exit(1)
