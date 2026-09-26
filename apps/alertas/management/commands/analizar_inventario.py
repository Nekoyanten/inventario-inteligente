"""Análisis nocturno: python manage.py analizar_inventario  (programar con cron)."""

from django.core.management.base import BaseCommand

from apps.alertas.motor import evaluar_negocio
from apps.core.models import Negocio
from apps.recomendaciones.services import generar_recomendaciones


class Command(BaseCommand):
    help = "Evalúa reglas de alertas y genera recomendaciones de compra para todos los negocios."

    def handle(self, *args, **options):
        for negocio in Negocio.objects.all():
            n_alertas = evaluar_negocio(negocio)
            n_recs = len(generar_recomendaciones(negocio))
            self.stdout.write(self.style.SUCCESS(f"{negocio}: {n_alertas} alertas, {n_recs} recomendaciones"))
