"""Envío de correos transaccionales (texto + HTML). Nunca rompe el flujo si el correo falla."""

import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

log = logging.getLogger(__name__)


def enviar(plantilla: str, asunto: str, destinatarios: list[str], contexto: dict | None = None) -> bool:
    destinatarios = [d for d in destinatarios if d]
    if not destinatarios:
        return False
    contexto = {"url": settings.URL_SITIO, "empresa": settings.EMPRESA, **(contexto or {})}
    try:
        msg = EmailMultiAlternatives(
            subject=asunto, body=render_to_string(f"correo/{plantilla}.txt", contexto),
            from_email=settings.DEFAULT_FROM_EMAIL, to=destinatarios,
        )
        msg.attach_alternative(render_to_string(f"correo/{plantilla}.html", contexto), "text/html")
        msg.send()
        return True
    except Exception:  # el correo es importante, pero no más que registrar el negocio o la venta
        log.exception("No se pudo enviar el correo '%s' a %s", plantilla, destinatarios)
        return False
