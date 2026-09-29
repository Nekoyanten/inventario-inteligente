"""Recetas: preparados que gastan insumos al venderse y productos elaborados (producción propia).

Todo cambio de stock pasa por registrar_movimiento (regla de oro)."""

from collections import defaultdict
from decimal import ROUND_DOWN, Decimal

from django.db import transaction

from apps.catalogo.models import Producto, RecetaItem, TipoProducto
from apps.core.auditoria import auditar

from .models import TipoMovimiento
from .services import ErrorInventario, permite_decimales, registrar_movimiento


def costo_receta(producto: Producto) -> Decimal:
    """Costo de una unidad según lo que cuestan hoy sus insumos (incluida la merma)."""
    return sum((item.costo for item in producto.receta.select_related("insumo")), Decimal("0")).quantize(Decimal("0.01"))


def disponibilidad(producto: Producto) -> Decimal | None:
    """Cuántas unidades de un preparado se pueden hacer con los insumos que hay. None si no tiene receta."""
    items = list(producto.receta.select_related("insumo"))
    if not items:
        return None
    posibles = [(i.insumo.stock_actual / i.cantidad_total) if i.cantidad_total else Decimal("Infinity") for i in items]
    return max(Decimal("0"), min(posibles)).quantize(Decimal("1"), rounding=ROUND_DOWN)


def disponibilidades(productos) -> dict[int, Decimal | None]:
    """disponibilidad() para varios preparados con dos consultas (punto de venta)."""
    ids = [p.pk for p in productos]
    por_producto = defaultdict(list)
    for item in RecetaItem.objects.filter(producto_id__in=ids).select_related("insumo"):
        por_producto[item.producto_id].append(item)
    resultado = {}
    for pid in ids:
        items = por_producto.get(pid)
        if not items:
            resultado[pid] = None
            continue
        resultado[pid] = max(Decimal("0"), min(i.insumo.stock_actual / i.cantidad_total for i in items if i.cantidad_total)
                             ).quantize(Decimal("1"), rounding=ROUND_DOWN)
    return resultado


def necesidades(lineas) -> dict[int, tuple[Producto, Decimal]]:
    """Insumos que gastan unas líneas de venta de preparados: {insumo_id: (insumo, cantidad)}."""
    total: dict[int, list] = {}
    for linea in lineas:
        producto, cantidad = linea["producto"], Decimal(str(linea["cantidad"]))
        for item in producto.receta.select_related("insumo"):
            actual = total.setdefault(item.insumo_id, [item.insumo, Decimal("0")])
            actual[1] += item.cantidad_total * cantidad
    return {k: (v[0], v[1]) for k, v in total.items()}


def validar_receta(producto: Producto, insumo: Producto):
    if insumo.pk == producto.pk:
        raise ErrorInventario("Un producto no puede ser insumo de sí mismo.")
    if insumo.negocio_id != producto.negocio_id:
        raise ErrorInventario("El insumo no pertenece a tu negocio.")
    if insumo.es_agrupador or insumo.es_preparado:
        raise ErrorInventario("El insumo debe tener stock propio (no puede ser un preparado ni un agrupador).")
    if producto.es_agrupador or producto.tipo == TipoProducto.INSUMO:
        raise ErrorInventario("Solo los productos y preparados llevan receta.")


@transaction.atomic
def guardar_item_receta(producto: Producto, insumo: Producto, cantidad, merma_pct=0, usuario=None) -> RecetaItem:
    validar_receta(producto, insumo)
    cantidad = Decimal(str(cantidad))
    if cantidad <= 0:
        raise ErrorInventario("La cantidad debe ser mayor que cero.")
    if cantidad != cantidad.to_integral_value() and not permite_decimales(insumo):
        raise ErrorInventario(f"{insumo.nombre} se maneja en unidades enteras: cámbiale la unidad (kg, L, botella…) "
                              "o usa una cantidad entera en la receta.")
    item, _ = RecetaItem.objects.update_or_create(producto=producto, insumo=insumo,
                                                  defaults={"cantidad": cantidad, "merma_pct": Decimal(str(merma_pct or 0))})
    actualizar_costo(producto)
    auditar(producto.negocio, usuario, "editar_receta", producto, insumo=insumo.pk, cantidad=str(cantidad))
    return item


def actualizar_costo(producto: Producto):
    """El costo de un preparado es el de su receta (así el margen y los reportes de utilidad son reales)."""
    if producto.es_preparado:
        Producto.objects.filter(pk=producto.pk).update(precio_compra=costo_receta(producto))


@transaction.atomic
def registrar_produccion(producto: Producto, cantidad, usuario, fecha=None, motivo="") -> list:
    """Elaboración propia: gasta los insumos de la receta y entra el producto terminado al costo de la receta."""
    if producto.tipo != TipoProducto.PRODUCTO:
        raise ErrorInventario("Solo se registra producción de productos con stock (los preparados se hacen al vender).")
    cantidad = Decimal(str(cantidad))
    if cantidad <= 0:
        raise ErrorInventario("La cantidad debe ser mayor que cero.")
    items = list(producto.receta.select_related("insumo"))
    if not items:
        raise ErrorInventario(f"{producto.nombre} no tiene receta: agrega sus insumos primero.")
    faltan = [f"{i.insumo.nombre} (hay {i.insumo.stock_actual:g}, se necesitan {i.cantidad_total * cantidad:g})"
              for i in items if i.insumo.stock_actual < i.cantidad_total * cantidad]
    if faltan:
        raise ErrorInventario("No alcanzan los insumos: " + "; ".join(faltan))
    costo = costo_receta(producto)
    movimientos = []
    for item in sorted(items, key=lambda i: i.insumo_id):  # orden fijo de bloqueo
        movimientos += registrar_movimiento(
            producto=item.insumo, tipo=TipoMovimiento.SALIDA_INSUMO, cantidad=item.cantidad_total * cantidad,
            usuario=usuario, fecha=fecha, motivo=f"Producción de {cantidad:g} {producto.nombre}",
            referencia_tipo="produccion", referencia_id=producto.pk)
    movimientos += registrar_movimiento(
        producto=producto, tipo=TipoMovimiento.ENTRADA_PRODUCCION, cantidad=cantidad, usuario=usuario, fecha=fecha,
        costo_unitario=costo, motivo=motivo or "Producción propia", referencia_tipo="produccion",
        referencia_id=producto.pk)
    Producto.objects.filter(pk=producto.pk).update(precio_compra=costo)
    auditar(producto.negocio, usuario, "registrar_produccion", producto, cantidad=str(cantidad), costo=str(costo))
    return movimientos
