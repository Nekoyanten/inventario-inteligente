"""Resumen diario por correo con las alertas críticas.  Programar: 0 7 * * * python manage.py enviar_resumen"""

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.template.loader import render_to_string

from apps.alertas.models import Alerta
from apps.core.models import Negocio
from apps.usuarios.models import Rol


class Command(BaseCommand):
    help = "Envía a los administradores un resumen de las alertas que requieren acción."

    def handle(self, *args, **opts):
        enviados = 0
        for negocio in Negocio.objects.filter(config__resumen_por_correo=True):
            alertas = list(Alerta.objects.filter(negocio=negocio, estado__in=["ABIERTA", "VISTA"],
                                                 severidad=Alerta.Severidad.ACTUAR).select_related("producto")[:30])
            destinatarios = list(negocio.usuarios.filter(rol=Rol.ADMIN, is_active=True).exclude(email="")
                                 .values_list("email", flat=True))
            if not alertas or not destinatarios:
                continue
            contexto = {"negocio": negocio, "alertas": alertas, "url": getattr(settings, "URL_SITIO", "")}
            send_mail(
                subject=f"{negocio.nombre}: {len(alertas)} alertas requieren tu atención",
                message=render_to_string("correo/resumen.txt", contexto),
                from_email=None, recipient_list=destinatarios,
                html_message=render_to_string("correo/resumen.html", contexto),
            )
            enviados += 1
        self.stdout.write(self.style.SUCCESS(f"Resúmenes enviados: {enviados}"))
