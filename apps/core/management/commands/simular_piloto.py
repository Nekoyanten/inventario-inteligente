"""Piloto simulado: 18 empresarios ficticios (3 por tipo de negocio) usando el sistema durante N días.

Todo pasa por los servicios reales (ventas, compras, conteos, alertas, recomendaciones). Sirve para
encontrar errores y fricciones antes de un piloto real. NO reemplaza la opinión de clientes reales.

    python manage.py simular_piloto --dias 60 --salida piloto.json
    python manage.py simular_piloto --giro FARMACIA --dias 20
"""

import json
import time
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.core.models import Negocio
from apps.core.simulacion.motor import SimuladorNegocio
from apps.core.simulacion.perfiles import PERFILES


class Command(BaseCommand):
    help = "Simula varios negocios ficticios usando el sistema durante un período (piloto simulado)."

    def add_arguments(self, parser):
        parser.add_argument("--dias", type=int, default=60)
        parser.add_argument("--semilla", type=int, default=7)
        parser.add_argument("--giro", help="Solo un tipo de negocio (MINIMERCADO, ROPA, …)")
        parser.add_argument("--clientes", nargs="*", help="Claves de perfil específicas")
        parser.add_argument("--salida", help="Archivo JSON con las métricas")
        parser.add_argument("--sin-fase8", action="store_true",
                            help="Simula el uso anterior a la Fase 8 (para comparar antes y después)")

    def handle(self, *args, **o):
        perfiles = [p for p in PERFILES if (not o["giro"] or p["giro"] == o["giro"].upper())
                    and (not o["clientes"] or p["clave"] in o["clientes"])]
        if not perfiles:
            raise CommandError("Ningún perfil coincide con el filtro.")
        inicio = timezone.localdate() - timedelta(days=o["dias"])
        resultados = []
        for perfil in perfiles:
            if Negocio.objects.filter(nombre=perfil["negocio"]).exists():
                raise CommandError(f"Ya existe «{perfil['negocio']}». Corre el piloto en una base de datos limpia.")
            t0 = time.monotonic()
            sim = SimuladorNegocio(perfil, inicio, o["dias"], o["semilla"], fase8=not o["sin_fase8"]).crear()
            for n in range(o["dias"]):
                sim.simular_dia(n)
            sim.cerrar()
            r = sim.resumen()
            r["segundos"] = round(time.monotonic() - t0, 1)
            resultados.append(r)
            self.stdout.write(
                f"{perfil['clave']:<24} {r['productos']:>4} prod · {r['ventas']['tickets']:>5} tickets · "
                f"quiebre top20 {r['quiebres']['pct_dias_agotado_top20']:>5}% · "
                f"divergencia {r['exactitud']['productos_con_diferencia']:>4} · {r['segundos']}s")
        if o["salida"]:
            with open(o["salida"], "w", encoding="utf-8") as f:
                json.dump(resultados, f, ensure_ascii=False, indent=1, default=str)
        self.stdout.write(self.style.SUCCESS(f"Piloto simulado: {len(resultados)} negocios."))
