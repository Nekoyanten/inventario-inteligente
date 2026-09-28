from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.inventario.models import TipoMovimiento
from apps.inventario.services import registrar_movimiento

from .models import DetalleVenta, Venta

MOTIVO_SIN_STOCK = "Venta sin stock registrado: mercancía en estantería que no estaba en el sistema"
FACTOR_INUSUAL = 5
MINIMO_INUSUAL = 5


@transaction.atomic
def registrar_venta(*, negocio, vendedor, lineas, medio_pago=Venta.MedioPago.EFECTIVO, cliente="", fecha=None,
                    evaluar_alertas=True, permitir_sin_stock=None):
    """Registra una venta y descuenta el inventario.

    lineas: lista de dicts {"producto": Producto, "cantidad": n, "precio_unitario": opcional, "descuento": opcional}

    Si el sistema no tiene stock suficiente:
    - con `permite_venta_sin_stock` (configuración del negocio), la venta se registra igual: se crea un ajuste
      positivo por lo que falta y una alerta para que el administrador lo revise (no se pierde la venta ni el dato);
    - si no, toda la venta se revierte (transacción).
    """
    from apps.catalogo.models import Producto
    from apps.inventario.services import ErrorInventario

    fecha = fecha or timezone.now()
    if permitir_sin_stock is None:
        config = getattr(negocio, "config", None)
        permitir_sin_stock = bool(config and config.permite_venta_sin_stock)
    if any(linea["producto"].negocio_id != negocio.pk for linea in lineas):
        raise ErrorInventario("Uno de los productos no pertenece a este negocio.")
    # Cantidad total por producto (una misma referencia puede venir en dos líneas)
    pedido: dict[int, Decimal] = {}
    for linea in lineas:
        pk = linea["producto"].pk
        pedido[pk] = pedido.get(pk, Decimal("0")) + Decimal(str(linea["cantidad"]))
    # Se bloquean las filas (siempre en el mismo orden) ANTES de calcular lo que falta: si dos cajas venden el mismo
    # producto a la vez, la segunda espera y calcula con el stock ya descontado por la primera.
    bloqueados = Producto.objects.select_for_update(of=("self",)).filter(pk__in=pedido).order_by("pk")
    faltantes = []
    for producto in bloqueados:
        falta = pedido[producto.pk] - producto.stock_actual
        if falta > 0:
            if not permitir_sin_stock:
                raise ErrorInventario(
                    f"Stock insuficiente de {producto.nombre}: hay {producto.stock_actual}, se piden {pedido[producto.pk]}.")
            faltantes.append((producto, falta))
    venta = Venta.objects.create(
        negocio=negocio, vendedor=vendedor, fecha=fecha, cliente=cliente, medio_pago=medio_pago
    )
    for producto, falta in faltantes:
        _ajuste_venta_sin_stock(producto, falta, vendedor, fecha, venta)
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
            evaluar_alertas=evaluar_alertas,
        )
        total += detalle.subtotal
    venta.total = total
    venta.save(update_fields=["total"])
    return venta


def _ajuste_venta_sin_stock(producto, falta, usuario, fecha, venta):
    from apps.alertas.models import Alerta
    from apps.core.formato import numero

    movs = registrar_movimiento(
        producto=producto, tipo=TipoMovimiento.ENTRADA_AJUSTE, cantidad=falta, usuario=usuario, fecha=fecha,
        motivo=MOTIVO_SIN_STOCK, referencia_tipo="venta_sin_stock", referencia_id=venta.pk, evaluar_alertas=False,
    )
    # Una sola alerta abierta por producto: se acumulan las ventas hasta que alguien la revise
    alerta = Alerta.objects.filter(producto=producto, tipo=Alerta.Tipo.VENTA_SIN_STOCK,
                                   estado__in=[Alerta.Estado.ABIERTA, Alerta.Estado.VISTA]).first()
    datos = alerta.datos if alerta else {"ventas": [], "cantidad": 0}
    datos["ventas"] = (datos.get("ventas", []) + [venta.pk])[-20:]
    datos["cantidad"] = float(datos.get("cantidad", 0)) + float(falta)
    datos["movimiento"] = movs[0].pk
    n = len(datos["ventas"])
    mensaje = (f"Se vendieron {numero(datos['cantidad'])} u. de {producto.nombre} que el sistema no tenía "
               f"({n} venta{'s' if n > 1 else ''}; la última por {usuario or 'usuario desconocido'}).")[:300]
    if alerta:
        alerta.datos, alerta.mensaje = datos, mensaje
        alerta.save(update_fields=["datos", "mensaje", "actualizado"])
    else:
        Alerta.objects.create(
            negocio=producto.negocio, producto=producto, tipo=Alerta.Tipo.VENTA_SIN_STOCK,
            severidad=Alerta.Severidad.REVISAR, mensaje=mensaje, datos=datos,
            accion_sugerida="¿Llegó una compra sin registrar? Regístrala; si no, revisa el kárdex o haz un conteo")


def cantidades_inusuales(lineas) -> list[dict]:
    """Líneas cuya cantidad supera FACTOR_INUSUAL veces lo que se suele vender del producto por venta.

    Sirve para pedir confirmación en el punto de venta (evita el clásico 20 en vez de 2)."""
    ids = [linea["producto"].pk for linea in lineas]
    habitual = limites_habituales(ids)
    avisos = []
    for linea in lineas:
        limite = habitual.get(linea["producto"].pk)
        cantidad = Decimal(str(linea["cantidad"]))
        if limite is not None and cantidad > limite:
            avisos.append({"producto": linea["producto"].pk, "nombre": linea["producto"].nombre,
                           "cantidad": float(cantidad), "habitual": float(limite)})
    return avisos


def limites_habituales(producto_ids) -> dict:
    """{producto_id: cantidad a partir de la cual se pide confirmación} según las últimas ventas (90 días)."""
    from datetime import timedelta

    from django.db.models import Avg, Count

    from .models import DetalleVenta

    desde = timezone.now() - timedelta(days=90)
    filas = (DetalleVenta.objects.filter(producto_id__in=producto_ids, venta__estado=Venta.Estado.COMPLETADA,
                                         venta__fecha__gte=desde)
             .values("producto_id").annotate(promedio=Avg("cantidad"), n=Count("id")))
    limites = {pid: Decimal(MINIMO_INUSUAL * 2) for pid in producto_ids}  # sin historia: umbral generoso
    for f in filas:
        if f["n"] >= 3:
            limites[f["producto_id"]] = max(Decimal(MINIMO_INUSUAL), Decimal(str(f["promedio"])) * FACTOR_INUSUAL)
    return limites


@transaction.atomic
def anular_venta(venta: Venta, usuario, motivo: str, fecha=None) -> Venta:
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
            fecha=fecha,
        )
        acumular_demanda_diaria(d.producto, dia, -d.cantidad)
    venta.estado = Venta.Estado.ANULADA
    venta.save(update_fields=["estado"])
    auditar(venta.negocio, usuario, "anular_venta", venta, motivo=motivo, total=str(venta.total))
    return venta
