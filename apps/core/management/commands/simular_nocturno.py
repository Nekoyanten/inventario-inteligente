"""Piloto simulado de vida nocturna: 9 negocios ficticios (3 bares, 3 discotecas, 3 bar-discotecas).

Todo pasa por los servicios reales (cuentas, cover, reservas, botellas, puntos, ofertas). Las conductas
de los clientes son SUPUESTOS (ver FACTOR_BOOST en apps/core/simulacion/nocturno.py): NO reemplaza un piloto real.

    python manage.py simular_nocturno --dias 60 --salida nocturno.json
    python manage.py simular_nocturno --giro BAR --sin-fidelizacion
"""

import json
import time

from django.core.management.base import BaseCommand, CommandError

from apps.core.models import Negocio
from apps.core.simulacion.nocturno import ejecutar
from apps.core.simulacion.perfiles_nocturnos import PERFILES_NOCTURNOS


class Command(BaseCommand):
    help = "Simula bares y discotecas ficticios usando el módulo nocturno durante N noches."

    def add_arguments(self, parser):
        parser.add_argument("--dias", type=int, default=60)
        parser.add_argument("--semilla", type=int, default=7)
        parser.add_argument("--giro", help="BAR, DISCOTECA o BAR_DISCOTECA")
        parser.add_argument("--clientes", nargs="*", help="Claves de perfil específicas")
        parser.add_argument("--salida", help="Archivo JSON con las métricas")
        parser.add_argument("--sin-fidelizacion", action="store_true",
                            help="El dueño no usa puntos, bonos, recordatorios ni ofertas (grupo de control)")

    def handle(self, *args, **o):
        perfiles = [p for p in PERFILES_NOCTURNOS if (not o["giro"] or p["giro"] == o["giro"].upper())
                    and (not o["clientes"] or p["clave"] in o["clientes"])]
        if not perfiles:
            raise CommandError("Ningún perfil coincide con el filtro.")
        resultados = []
        for perfil in perfiles:
            if Negocio.objects.filter(nombre=perfil["negocio"]).exists():
                raise CommandError(f"Ya existe «{perfil['negocio']}». Corre el piloto en una base de datos limpia.")
            t0 = time.monotonic()
            r = ejecutar(perfil, o["dias"], o["semilla"], fidelizacion=not o["sin_fidelizacion"])
            r["segundos"] = round(time.monotonic() - t0, 1)
            resultados.append(r)
            self.stdout.write(f"{perfil['clave']:<22} ventas {r['ventas']:>12,.0f} · pour cost {r['pour_cost']}% · "
                              f"vuelven {r['vuelven_pct']}% · {r['segundos']}s")
        if o["salida"]:
            with open(o["salida"], "w", encoding="utf-8") as f:
                json.dump(resultados, f, ensure_ascii=False, indent=1, default=str)
        self.stdout.write(self.style.SUCCESS(f"Piloto nocturno simulado: {len(resultados)} negocios."))
