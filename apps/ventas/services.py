from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.inventario.models import TipoMovimiento
from apps.inventario.services import registrar_movimiento

from .models import DetalleVenta, Venta


@transaction.atomic
def registrar_venta(*, negocio, vendedor, lineas, medio_pago=Venta.MedioPago.EFECTIVO, cliente="", fecha=None):
    """Registra una venta y descuenta el inventario.

    lineas: lista de dicts {"producto": Producto, "cantidad": n, "precio_unitario": opcional, "descuento": opcional}
    Si algún producto no tiene stock, toda la venta se revierte (transacción).
    """
    fecha = fecha or timezone.now()
    venta = Venta.objects.create(
        negocio=negocio, vendedor=vendedor, fecha=fecha, cliente=cliente, medio_pago=medio_pago
    )
    total = Decimal("0")
    for linea in lineas:
        producto = linea["producto"]
        detalle = DetalleVenta.objects.create(
            venta=venta,
            producto=producto,
            cantidad=Decimal(str(linea["cantidad"])),
            precio_unitario=Decimal(str(linea.get("precio_unitario", producto.precio_venta))),
            costo_unitario=producto.precio_compra,
            descuento=Decimal(str(linea.get("descuento", 0))),
        )
        registrar_movimiento(
            producto=producto,
            tipo=TipoMovimiento.SALIDA_VENTA,
            cantidad=detalle.cantidad,
            usuario=vendedor,
            fecha=fecha,
            motivo=f"Venta #{venta.pk}",
            referencia_tipo="venta",
            referencia_id=venta.pk,
        )
        total += detalle.subtotal
    venta.total = total
    venta.save(update_fields=["total"])
    return venta
