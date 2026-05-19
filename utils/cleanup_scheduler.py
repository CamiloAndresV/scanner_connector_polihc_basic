#utils/cleanup_scheduler.py

"""
este módulo programa una tarea de limpieza automática usando APScheduler.
más robusto y confiable que threading.Timer para tareas recurrentes.
"""

# 1. Standard library imports
import logging
from typing import Optional

# 2. Third party imports
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR

# 3. First party (local) imports
from controllers.scan_controller import perform_cleanup
from config.settings import settings

# Configuración del logger para este módulo
logger = logging.getLogger(__name__)


def schedule_cleanup(hour: Optional[int] = None, minute: Optional[int] = None):
    """
    Programa limpieza diaria de sesiones usando APScheduler.

    Args:
        hour (int): Hora del día (0-23, default: 15)
        minute (int): Minuto de la hora (0-59, default: 30)
    
    Returns:
        BackgroundScheduler: Instancia del scheduler iniciado
        
    Note:
        El scheduler se ejecuta en background y no bloquea el thread principal.
        Solo permite 1 instancia del job corriendo simultáneamente.
    """
    # Resolver configuración (si no se pasa por parámetro usa .env)
    if hour is None:
        hour = settings.cleanup_schedule_hour
    if minute is None:
        minute = settings.cleanup_schedule_minute

    # Verificar si el servidor se está apagando
    try:
        from app import _server_shutting_down
        if _server_shutting_down:
            logger.info("[SCHEDULE] Servidor apagándose, no se programa cleanup")
            return None
    except ImportError:
        logger.warning("[SCHEDULE] No se pudo importar flag de shutdown, continuando...")
    
    # Crear scheduler en background (no bloquea el thread principal)
    scheduler = BackgroundScheduler()
    
    # Job de limpieza con wrapper que verifica shutdown
    def safe_cleanup_wrapper():
        """Ejecuta cleanup solo si el servidor NO se está apagando."""
        try:
            from app import _server_shutting_down
            if _server_shutting_down:
                logger.info("[AUTO-CLEANUP] Servidor apagándose, cancelando cleanup")
                return
        except ImportError:
            pass
        
        # Ejecutar limpieza segura: no tocar sesiones activas en curso.
        logger.info("[AUTO-CLEANUP] Iniciando limpieza programada...")
        perform_cleanup(force=False)

    # Agregar job con trigger cron diario
    scheduler.add_job(
        func=safe_cleanup_wrapper,
        trigger=CronTrigger(hour=hour, minute=minute),
        id='daily_cleanup',
        name='Limpieza diaria de sesiones y archivos',
        replace_existing=True,
        max_instances=1  # Solo una instancia corriendo a la vez
    )

    # Event listeners para logging
    def job_executed(_event):
        logger.info("✅ Limpieza automática completada exitosamente")

    def job_error(event):
        logger.error("Error en la limpieza automática: %s", event.exception)

    # Agregar listeners al scheduler
    scheduler.add_listener(job_executed, EVENT_JOB_EXECUTED)
    scheduler.add_listener(job_error, EVENT_JOB_ERROR)

    # Iniciar scheduler
    scheduler.start()

    # Log de confirmación
    job = scheduler.get_job('daily_cleanup')
    if job:
        logger.info(f"🕐 Limpieza automática programada diariamente a las {hour:02d}:{minute:02d}")
        logger.info(f"📅 Próxima ejecución: {job.next_run_time}")
    else:
        logger.warning("⚠️ No se pudo obtener información del job programado")

    return scheduler
