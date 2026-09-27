"""Reglas de negocio del inventario.

REGLA DE ORO: este es el ÚNICO módulo que modifica Producto.stock_actual.
"""

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.catalogo.models import Producto
from apps.core.auditoria import auditar

from .models import TIPOS_CON_MOTIVO_OBLIGATORIO, ConteoFisico, Lote, Movimiento, TipoMovimiento


class ErrorInventario(Exception):
    pass


@transaction.atomic
def registrar_movimiento(
    *,
    producto: Producto,
    tipo: str,
    cantidad,
    usuario=None,
    motivo: str = "",
    fecha=None,
    costo_unitario=None,
    lote: Lote | None = None,
    fecha_vencimiento=None,
    referencia_tipo: str = "",
    referencia_id: int | None = None,
    evaluar_alertas: bool = True,
) -> list[Movimiento]:
    """Registra un movimiento y actualiza el stock de forma atómica.

    - Bloquea la fila del producto (select_for_update) para evitar condiciones de carrera.
    - Si el negocio usa lotes: las entradas crean/alimentan un lote y las salidas consumen FEFO,
      por lo que una salida puede generar varios movimientos (uno por lote).
    - Devuelve la lista de movimientos creados.
    """
    cantidad = Decimal(str(cantidad))
    if cantidad <= 0:
        raise ErrorInventario("La cantidad debe ser mayor que cero.")
    if tipo in TIPOS_CON_MOTIVO_OBLIGATORIO and not motivo.strip():
        raise ErrorInventario("Este tipo de movimiento requiere un motivo.")

    producto = Producto.objects.select_for_update().select_related("negocio__config").get(pk=producto.pk)
    config = getattr(producto.negocio, "config", None)
    usa_lotes = bool(config and config.usa_lotes)
    es_entrada = TipoMovimiento.es_entrada(tipo)
    fecha = fecha or timezone.now()
    costo = Decimal(str(costo_unitario)) if costo_unitario is not None else producto.precio_compra

    if not es_entrada and cantidad > producto.stock_actual:
        raise ErrorInventario(
            f"Stock insuficiente de {producto.nombre}: hay {producto.stock_actual}, se piden {cantidad}."
        )

    # Reparto por lotes
    tramos: list[tuple[Lote | None, Decimal]] = []
    if usa_lotes and es_entrada:
        if lote is None:
            lote = Lote.objects.create(producto=producto, fecha_vencimiento=fecha_vencimiento, costo_unitario=costo)
        lote.cantidad += cantidad
        lote.save(update_fields=["cantidad", "actualizado"])
        tramos.append((lote, cantidad))
    elif usa_lotes and not es_entrada:
        restante = cantidad
        lotes = [lote] if lote else Lote.objects.select_for_update().filter(producto=producto, cantidad__gt=0)
        for l in lotes:  # ya vienen ordenados FEFO
            if restante <= 0:
                break
            tomar = min(l.cantidad, restante)
            l.cantidad -= tomar
            l.save(update_fields=["cantidad", "actualizado"])
            tramos.append((l, tomar))
            restante -= tomar
        if restante > 0:  # stock sin lote asignado (p. ej. inventario anterior a activar lotes)
            tramos.append((None, restante))
    else:
        tramos.append((None, cantidad))

    movimientos = []
    stock = producto.stock_actual
    for l, cant in tramos:
        stock = stock + cant if es_entrada else stock - cant
        movimientos.append(
            Movimiento.objects.create(
                negocio=producto.negocio,
                producto=producto,
                lote=l,
                tipo=tipo,
                cantidad=cant,
                costo_unitario=costo,
                stock_resultante=stock,
                fecha=fecha,
                usuario=usuario,
                motivo=motivo,
                referencia_tipo=referencia_tipo,
                referencia_id=referencia_id,
            )
        )

    producto.stock_actual = stock
    producto.save(update_fields=["stock_actual", "actualizado"])

    if es_entrada and tipo == TipoMovimiento.ENTRADA_COMPRA and costo_unitario is not None:
        producto.precio_compra = costo  # último costo
        producto.save(update_fields=["precio_compra"])

    if tipo == TipoMovimiento.SALIDA_VENTA:
        from apps.analitica.services import acumular_demanda_diaria

        dia = timezone.localdate(fecha) if hasattr(fecha, "tzinfo") and fecha.tzinfo else getattr(fecha, "date", lambda: fecha)()
        acumular_demanda_diaria(producto, dia, cantidad)

    if evaluar_alertas:
        from apps.alertas.motor import evaluar_producto

        transaction.on_commit(lambda: evaluar_producto(producto.pk))

    return movimientos


def kardex(producto: Producto, desde=None, hasta=None):
    """Historial de movimientos: responde '¿por qué tengo solo 8 unidades?'."""
    qs = producto.movimientos.select_related("usuario", "lote").order_by("fecha", "id")
    if desde:
        qs = qs.filter(fecha__gte=desde)
    if hasta:
        qs = qs.filter(fecha__lte=hasta)
    return qs


@transaction.atomic
def aprobar_conteo(conteo: ConteoFisico, aprobado_por) -> list[Movimiento]:
    """Convierte las diferencias de un conteo físico en movimientos de ajuste."""
    if conteo.estado != ConteoFisico.Estado.PENDIENTE_APROBACION:
        raise ErrorInventario("Solo se pueden aprobar conteos pendientes.")
    movimientos = []
    for d in conteo.detalles.select_related("producto"):
        if d.diferencia == 0:
            continue
        if not d.motivo.strip():
            raise ErrorInventario(f"Falta el motivo de la diferencia en {d.producto.nombre}.")
        tipo = TipoMovimiento.ENTRADA_AJUSTE if d.diferencia > 0 else TipoMovimiento.SALIDA_AJUSTE
        movimientos += registrar_movimiento(
            producto=d.producto,
            tipo=tipo,
            cantidad=abs(d.diferencia),
            usuario=aprobado_por,
            motivo=f"Conteo #{conteo.pk}: {d.motivo}",
            referencia_tipo="conteo",
            referencia_id=conteo.pk,
        )
    conteo.estado = ConteoFisico.Estado.APROBADO
    conteo.aprobado_por = aprobado_por
    conteo.save()
    auditar(conteo.negocio, aprobado_por, "aprobar_conteo", conteo, ajustes=len(movimientos))
    return movimientos
