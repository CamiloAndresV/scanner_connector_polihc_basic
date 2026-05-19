#!/usr/bin/env python
# scripts/security_audit.py
"""
Script para ejecutar auditoría de seguridad de dependencias localmente.
Ejecutar desde la raíz del proyecto: python scripts/security_audit.py
"""

import subprocess
import sys

def run_command(cmd, description):
    """Ejecuta un comando y muestra el resultado."""
    print(f"\n{'='*60}")
    print(f"🔍 {description}")
    print('='*60)
    
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True
        )
        
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
            
        return result.returncode == 0
    except Exception as e:
        print(f"❌ Error ejecutando comando: {e}")
        return False

def main():
    print("🔒 Scanner Connector API - Auditoría de Seguridad")
    print("="*60)
    
    # Verificar si pip-audit está instalado
    try:
        subprocess.run(
            ["pip", "show", "pip-audit"],
            capture_output=True,
            check=True
        )
    except subprocess.CalledProcessError:
        print("📦 Instalando pip-audit...")
        subprocess.run([sys.executable, "-m", "pip", "install", "pip-audit"])
    
    results = []
    
    # Ejecutar pip-audit
    success = run_command(
        "pip-audit -r requirements.txt --desc on",
        "Ejecutando pip-audit (vulnerabilidades conocidas)"
    )
    results.append(("pip-audit", success))
    
    # Resumen
    print(f"\n{'='*60}")
    print("📊 RESUMEN DE AUDITORÍA")
    print('='*60)
    
    for tool, passed in results:
        status = "✅ Sin vulnerabilidades" if passed else "⚠️ Revisar resultados"
        print(f"  {tool}: {status}")
    
    all_passed = all(r[1] for r in results)
    
    if all_passed:
        print("\n✅ Todas las auditorías pasaron correctamente")
        return 0
    else:
        print("\n⚠️ Se encontraron posibles vulnerabilidades. Revisar logs arriba.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
