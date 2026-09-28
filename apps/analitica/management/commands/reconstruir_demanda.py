"""Recalcula DemandaDiaria desde las ventas completadas y el consumo interno (tras importar datos o corregir errores)."""

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.analitica.models import DemandaDiaria
from apps.inventario.models import Movimiento, TipoMovimiento
from apps.ventas.models import DetalleVenta, Venta


class Command(BaseCommand):
    help = "Reconstruye la demanda diaria a partir de las ventas (excluye anuladas)."

    def add_arguments(self, parser):
        parser.add_argument("--negocio", type=int, help="Solo este negocio (id)")

    @transaction.atomic
    def handle(self, *args, **opts):
        ventas = DetalleVenta.objects.filter(venta__estado=Venta.Estado.COMPLETADA)
        demanda = DemandaDiaria.objects.all()
        if opts.get("negocio"):
            ventas = ventas.filter(venta__negocio_id=opts["negocio"])
            demanda = demanda.filter(producto__negocio_id=opts["negocio"])
        consumos = Movimiento.objects.filter(tipo=TipoMovimiento.SALIDA_CONSUMO_INTERNO)
        if opts.get("negocio"):
            consumos = consumos.filter(negocio_id=opts["negocio"])
        demanda.delete()
        totales: dict[tuple, float] = {}
        tz = timezone.get_current_timezone()
        for pid, fecha, cant in ventas.values_list("producto_id", "venta__fecha", "cantidad"):
            clave = (pid, fecha.astimezone(tz).date())
            totales[clave] = totales.get(clave, 0) + cant
        for pid, fecha, cant in consumos.values_list("producto_id", "fecha", "cantidad"):
            clave = (pid, fecha.astimezone(tz).date())
            totales[clave] = totales.get(clave, 0) + cant
        DemandaDiaria.objects.bulk_create(
            [DemandaDiaria(producto_id=p, fecha=f, cantidad=c) for (p, f), c in totales.items()], batch_size=1000
        )
        self.stdout.write(self.style.SUCCESS(f"{len(totales)} registros de demanda diaria reconstruidos."))
