"""Envoltorio para registrar las tareas programadas y reportar sus errores."""

import logging
from contextlib import contextmanager

from django.utils import timezone

log = logging.getLogger(__name__)


@contextmanager
def registrar_tarea(nombre: str):
    from .models import EjecucionTarea

    ejec = EjecucionTarea.objects.create(nombre=nombre)
    resumen = []
    try:
        yield resumen
        ejec.ok = True
    except Exception as e:
        ejec.detalle = f"{type(e).__name__}: {e}"
        log.exception("La tarea %s falló", nombre)  # Sentry la recibe por el logging de errores
        raise
    finally:
        ejec.fin = timezone.now()
        if ejec.ok:
            ejec.detalle = "\n".join(resumen)[:5000]
        ejec.save()
