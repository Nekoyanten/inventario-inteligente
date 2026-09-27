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
    for linea in sorted(lineas, key=lambda linea_: linea_["producto"].pk):
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


@transaction.atomic
def anular_venta(venta: Venta, usuario, motivo: str) -> Venta:
    """Revierte el inventario (devolución de cliente) y descuenta la demanda registrada."""
    from apps.analitica.services import acumular_demanda_diaria
    from apps.core.auditoria import auditar

    if venta.estado == Venta.Estado.ANULADA:
        raise ValueError("La venta ya está anulada.")
    if not motivo.strip():
        raise ValueError("Indica el motivo de la anulación.")
    dia = timezone.localdate(venta.fecha)
    for d in venta.detalles.select_related("producto"):
        registrar_movimiento(
            producto=d.producto, tipo=TipoMovimiento.ENTRADA_DEVOLUCION_CLIENTE, cantidad=d.cantidad, usuario=usuario,
            motivo=f"Anulación venta #{venta.pk}: {motivo}", referencia_tipo="venta", referencia_id=venta.pk,
        )
        acumular_demanda_diaria(d.producto, dia, -d.cantidad)
    venta.estado = Venta.Estado.ANULADA
    venta.save(update_fields=["estado"])
    auditar(venta.negocio, usuario, "anular_venta", venta, motivo=motivo, total=str(venta.total))
    return venta
