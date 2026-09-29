"""Carga 5 negocios de demostración, cada uno con su usuario, su plan, un proveedor de marca real, más de 100 clientes
y el historial de N días (simulado con los servicios reales de la aplicación).

    python manage.py cargar_demo_negocios              # 60 días (tarda unos minutos)
    python manage.py cargar_demo_negocios --dias 30    # más rápido
    python manage.py cargar_demo_negocios --borrar     # elimina los negocios de demostración

Usuarios (clave: Demo2026!):
    bar.lacuadra      Bar La Cuadra             bar            Emprendedor   proveedor Bavaria
    disco.kalima      Kalima Club               discoteca      Negocio       proveedor Diageo
    bardisco.mirador  Mirador 360 Bar & Disco   bar-discoteca  Negocio       proveedor Industria Licorera de Caldas
    ropa.denim        Denim Store Pasto         ropa           Emprendedor   proveedor Levi's
    vape.nube         Nube Vape Shop            vapeadores     Gratis        proveedor Vaporesso (+ Nasty Juice)

Negocios, dueños y clientes son inventados; las marcas y productos existen y los precios son aproximados.
"""

import time
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.core.models import Negocio
from apps.core.simulacion import demo_negocios as demo
from apps.usuarios.models import Usuario


class Command(BaseCommand):
    help = "Crea 5 negocios de demostración (bar, discoteca, bar-discoteca, ropa y vapeadores) con historial simulado."

    def add_arguments(self, parser):
        parser.add_argument("--dias", type=int, default=60)
        parser.add_argument("--semilla", type=int, default=7)
        parser.add_argument("--solo", nargs="*", help="Usuarios a crear (p. ej. vape.nube ropa.denim)")
        parser.add_argument("--borrar", action="store_true", help="Elimina los negocios de demostración y sale")

    def handle(self, *args, **o):
        if o["borrar"]:
            from apps.core.cierre import eliminar_negocio

            for n in Negocio.objects.filter(nombre__in=demo.negocios_demo()):
                eliminar_negocio(n)
                self.stdout.write(f"Eliminado: {n.nombre}")
            return
        solo = set(o["solo"] or demo.usuarios_demo())
        ya = Usuario.objects.filter(username__in=solo).values_list("username", flat=True)
        if ya:
            raise CommandError(f"Ya existen: {', '.join(ya)}. Usa --borrar primero.")
        dias, semilla = o["dias"], o["semilla"]
        filas = []
        for perfil in demo.NOCTURNOS_DEMO + demo.TIENDAS_DEMO:
            if perfil["usuario"] not in solo:
                continue
            t0 = time.monotonic()
            self.stdout.write(f"→ {perfil['negocio']} ({dias} días)…")
            if perfil["giro"] in ("BAR", "DISCOTECA", "BAR_DISCOTECA"):
                from apps.core.simulacion.nocturno import SimuladorNocturno

                inicio = timezone.localdate() - timedelta(days=dias)
                sim = SimuladorNocturno(perfil, inicio, dias, semilla).crear()
                for n in range(dias):
                    sim.simular_noche(n)
                sim.cerrar()
            else:
                from apps.core.simulacion.tienda import ejecutar_tienda

                sim = ejecutar_tienda(perfil, dias, semilla)
            negocio = sim.negocio
            from apps.alertas.motor import evaluar_negocio
            from apps.recomendaciones.services import generar_recomendaciones

            evaluar_negocio(negocio)
            generar_recomendaciones(negocio)
            extra = demo.personalizar(negocio, semilla, perfil["satisfaccion"])
            demo.aplicar_plan(negocio, perfil["plan"])
            filas.append(self._fila(negocio, perfil, extra, time.monotonic() - t0))
        self.stdout.write("")
        for f in filas:
            self.stdout.write(f)
        self.stdout.write(self.style.SUCCESS(f"Listo: {len(filas)} negocios. Clave de todos los usuarios: {demo.CLAVE_DEMO}"))

    def _fila(self, negocio, perfil, extra, segundos) -> str:
        from apps.catalogo.models import Producto
        from apps.clientes import analisis
        from apps.ventas.models import Venta

        lim = negocio.suscripcion.limites
        r = analisis.resumen(negocio)
        productos = Producto.objects.filter(negocio=negocio, es_agrupador=False).count()
        usuarios = Usuario.objects.filter(negocio=negocio, is_active=True).count()
        ventas = Venta.objects.filter(negocio=negocio, estado="COMPLETADA").count()
        return (f"{perfil['usuario']:<18} {negocio.nombre:<26} plan {lim['nombre']:<11} "
                f"productos {productos}/{lim['productos']} · usuarios {usuarios}/{lim['usuarios']} · "
                f"{extra['clientes']} clientes · {ventas} ventas · {r['ventas_identificadas_pct']}% con cliente · "
                f"{r['recurrentes_pct']}% vuelven · {segundos:.0f}s")
