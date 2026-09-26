from django.db import transaction
from django.utils import timezone

from apps.core.auditoria import auditar
from apps.inventario.models import TipoMovimiento
from apps.inventario.services import ErrorInventario, registrar_movimiento

from .models import OrdenCompra


def enviar_orden(orden: OrdenCompra, usuario):
    if orden.estado != OrdenCompra.Estado.BORRADOR:
        raise ErrorInventario("Solo se envían órdenes en borrador.")
    orden.estado = OrdenCompra.Estado.ENVIADA
    orden.fecha_envio = timezone.now()
    orden.save()
    auditar(orden.negocio, usuario, "enviar_orden", orden)
    return orden


@transaction.atomic
def recibir_orden(orden: OrdenCompra, usuario, recibido: dict, numero_factura="", vencimientos: dict | None = None):
    """Registra la recepción (total o parcial) de una orden.

    recibido: {detalle_id: cantidad}; vencimientos: {detalle_id: date} (si el negocio usa vencimientos)
    """
    if orden.estado not in (
        OrdenCompra.Estado.ENVIADA,
        OrdenCompra.Estado.CONFIRMADA,
        OrdenCompra.Estado.RECIBIDA_PARCIAL,
    ):
        raise ErrorInventario("La orden no está en un estado que permita recepción.")
    vencimientos = vencimientos or {}
    ahora = timezone.now()
    for detalle in orden.detalles.select_related("producto"):
        cant = recibido.get(detalle.pk, 0)
        if not cant:
            continue
        if cant > detalle.pendiente:
            raise ErrorInventario(f"Se recibe más de lo pedido en {detalle.producto.nombre}.")
        registrar_movimiento(
            producto=detalle.producto,
            tipo=TipoMovimiento.ENTRADA_COMPRA,
            cantidad=cant,
            usuario=usuario,
            costo_unitario=detalle.costo_unitario,
            fecha_vencimiento=vencimientos.get(detalle.pk),
            motivo=f"OC #{orden.pk} {numero_factura}".strip(),
            referencia_tipo="orden_compra",
            referencia_id=orden.pk,
        )
        detalle.cantidad_recibida += cant
        detalle.save(update_fields=["cantidad_recibida"])

    completa = all(d.pendiente <= 0 for d in orden.detalles.all())
    orden.estado = OrdenCompra.Estado.RECIBIDA if completa else OrdenCompra.Estado.RECIBIDA_PARCIAL
    orden.numero_factura = numero_factura or orden.numero_factura
    if completa:
        orden.fecha_recepcion = ahora
        if orden.fecha_envio:
            orden.dias_entrega = max(0, (ahora - orden.fecha_envio).days)
    orden.save()
    auditar(orden.negocio, usuario, "recibir_orden", orden, completa=completa)
    return orden
