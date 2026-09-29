"""Análisis nocturno: python manage.py analizar_inventario  (programar con cron)."""

from django.core.management.base import BaseCommand

from apps.alertas.motor import evaluar_negocio
from apps.analitica.services import registrar_y_evaluar_pronosticos
from apps.core.models import Negocio
from apps.recomendaciones.services import generar_recomendaciones


class Command(BaseCommand):
    help = "Evalúa reglas de alertas y genera recomendaciones de compra para todos los negocios."

    def handle(self, *args, **options):
        from apps.core.tareas import registrar_tarea

        with registrar_tarea("analizar_inventario") as resumen:
            for negocio in Negocio.objects.all():
                try:
                    n_alertas = evaluar_negocio(negocio)
                    n_recs = len(generar_recomendaciones(negocio))
                    registrar_y_evaluar_pronosticos(negocio)
                    if negocio.giro in ("BAR", "DISCOTECA", "BAR_DISCOTECA"):
                        from apps.nocturno.services import reservas_vencidas, vencer_botellas

                        vencer_botellas(negocio)
                        reservas_vencidas(negocio)
                except Exception:  # un negocio con datos raros no debe frenar el análisis de los demás
                    import logging

                    logging.getLogger(__name__).exception("Falló el análisis de %s", negocio)
                    resumen.append(f"ERROR en {negocio}")
                    continue
                linea = f"{negocio}: {n_alertas} alertas, {n_recs} recomendaciones"
                resumen.append(linea)
                self.stdout.write(self.style.SUCCESS(linea))
