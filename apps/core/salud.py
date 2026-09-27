"""Verificaciones del estado de la plataforma: base de datos, caché, almacenamiento, correo y tareas nocturnas."""

import time
import uuid

from django.conf import settings
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import connection
from django.utils import timezone


def _medir(funcion):
    t = time.perf_counter()
    try:
        detalle = funcion()
        return {"ok": True, "ms": round((time.perf_counter() - t) * 1000), "detalle": detalle or ""}
    except Exception as e:  # noqa: BLE001 - se reporta el error como dato
        return {"ok": False, "ms": round((time.perf_counter() - t) * 1000), "detalle": f"{type(e).__name__}: {e}"[:200]}


def base_de_datos():
    with connection.cursor() as c:
        c.execute("SELECT 1")
    return connection.vendor


def cache_():
    clave = f"salud-{uuid.uuid4().hex}"
    cache.set(clave, "ok", 10)
    if cache.get(clave) != "ok":
        raise RuntimeError("la caché no devolvió el valor")
    backend = settings.CACHES["default"]["BACKEND"].rsplit(".", 1)[-1]
    return backend + ("" if "Redis" in backend else " (solo este proceso)")


def almacenamiento():
    nombre = default_storage.save(f"salud/{uuid.uuid4().hex}.txt", ContentFile(b"ok"))
    default_storage.delete(nombre)
    return "nube (S3 compatible)" if settings.ALMACENAMIENTO_NUBE else "disco local"


def tareas_nocturnas():
    from .models import EjecucionTarea

    ultima = EjecucionTarea.objects.filter(nombre="analizar_inventario").first()
    if ultima is None:
        return "el análisis nocturno aún no se ha ejecutado"
    horas = (timezone.now() - ultima.inicio).total_seconds() / 3600
    if not ultima.ok:
        raise RuntimeError(f"el último análisis falló: {ultima.detalle[:120]}")
    if horas > 26:
        raise RuntimeError(f"el análisis nocturno no corre hace {horas:.0f} horas (revisa el cron)")
    return f"último análisis hace {horas:.0f} h ({ultima.duracion_s} s)"


NOMBRES = {"base_de_datos": "Base de datos", "cache": "Caché", "almacenamiento": "Imágenes",
           "tareas": "Análisis nocturno"}


def revisar(completo=False) -> dict:
    resultado = {"base_de_datos": _medir(base_de_datos), "cache": _medir(cache_)}
    if completo:
        resultado["almacenamiento"] = _medir(almacenamiento)
        resultado["tareas"] = _medir(tareas_nocturnas)
    for clave, valor in resultado.items():
        valor["nombre"] = NOMBRES[clave]
    resultado["ok"] = all(v["ok"] for v in resultado.values() if isinstance(v, dict))
    return resultado


def configuracion() -> list[dict]:
    """Lista de chequeo de la puesta en producción (lo que falta configurar)."""
    return [
        {"nombre": "Modo producción (DEBUG=False)", "ok": not settings.DEBUG},
        {"nombre": "Imágenes en la nube (AWS_STORAGE_BUCKET_NAME)", "ok": settings.ALMACENAMIENTO_NUBE,
         "ayuda": "Sin bucket, las imágenes se pierden en cada despliegue de Render/Docker."},
        {"nombre": "Correo (EMAIL_URL)", "ok": settings.CORREO_CONFIGURADO,
         "ayuda": "Necesario para recuperar contraseñas, bienvenida y resumen diario."},
        {"nombre": "Monitoreo de errores (SENTRY_DSN)", "ok": bool(settings.SENTRY_DSN),
         "ayuda": "Te avisa por correo cuando algo falla a un cliente."},
        {"nombre": "Caché compartida (CACHE_URL con Redis)", "ok": "redis" in settings.CACHES["default"]["BACKEND"].lower(),
         "ayuda": "Recomendado con varios procesos: el límite de intentos de ingreso se comparte."},
        {"nombre": "URL pública (URL_SITIO)", "ok": not settings.URL_SITIO.startswith("http://localhost"),
         "ayuda": "Se usa en los enlaces de los correos."},
        {"nombre": "WhatsApp comercial (CONTACTO_VENTAS)", "ok": bool(settings.CONTACTO_VENTAS)},
        {"nombre": "Datos legales de la empresa (EMPRESA_NIT, EMPRESA_CORREO)",
         "ok": bool(settings.EMPRESA["nit"]) and "example.com" not in settings.EMPRESA["correo"]},
    ]
