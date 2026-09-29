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
                    evaluar_alertas=True, permitir_sin_stock=None, cliente_ref=None, puntos_canjear=0,
                    descuento_general_pct=0, propina=0, pagado_con_credito=0):
    """Registra una venta y descuenta el inventario.

    lineas: lista de dicts {"producto": Producto, "cantidad": n, "precio_unitario": opcional, "descuento": opcional}

    - Preparados (un almuerzo, un servicio): se descuentan los insumos de su receta.
    - Con cliente (`cliente_ref`): se aplican sus ofertas vigentes, se canjean los puntos pedidos y gana puntos.
    - Si el sistema no tiene stock suficiente: con `permite_venta_sin_stock` se registra igual (ajuste + alerta para
      revisar); si no, toda la venta se revierte (transacción).
    """
    from apps.catalogo.models import Producto
    from apps.clientes.services import cotizar, puntos_por_compra, registrar_compra
    from apps.inventario.recetas import costo_receta
    from apps.inventario.services import ErrorInventario

    fecha = fecha or timezone.now()
    if permitir_sin_stock is None:
        config = getattr(negocio, "config", None)
        permitir_sin_stock = bool(config and config.permite_venta_sin_stock)
    if any(linea["producto"].negocio_id != negocio.pk for linea in lineas):
        raise ErrorInventario("Uno de los productos no pertenece a este negocio.")
    lineas = [{**linea, "producto": Producto.objects.get(pk=linea["producto"].pk)} for linea in lineas]
    for linea in lineas:
        p = linea["producto"]
        if p.es_insumo or p.es_agrupador:
            raise ErrorInventario(f"{p.nombre} no se vende directamente"
                                  f"{' (es un insumo)' if p.es_insumo else ' (elige una variante)'}.")

    # Qué sale del inventario: los productos con stock y, por cada preparado, los insumos de su receta
    salidas: dict[int, list] = {}
    for linea in lineas:
        p, cantidad = linea["producto"], Decimal(str(linea["cantidad"]))
        if p.es_preparado:
            for item in p.receta.select_related("insumo"):
                fila = salidas.setdefault(item.insumo_id, [item.insumo, Decimal("0"), TipoMovimiento.SALIDA_INSUMO])
                fila[1] += item.cantidad_total * cantidad
        else:
            fila = salidas.setdefault(p.pk, [p, Decimal("0"), TipoMovimiento.SALIDA_VENTA])
            fila[1] += cantidad
    # Se bloquean las filas (siempre en el mismo orden) ANTES de calcular lo que falta: si dos cajas venden el mismo
    # producto o insumo a la vez, la segunda espera y calcula con el stock ya descontado por la primera.
    for bloqueado in Producto.objects.select_for_update(of=("self",)).filter(pk__in=salidas).order_by("pk"):
        salidas[bloqueado.pk][0] = bloqueado
    faltantes = []
    for producto, requerido, _tipo in salidas.values():
        falta = requerido - producto.stock_actual
        if falta > 0:
            if not permitir_sin_stock:
                raise ErrorInventario(
                    f"Stock insuficiente de {producto.nombre}: hay {producto.stock_actual}, se piden {requerido}.")
            faltantes.append((producto, falta))

    # Precios: precios por horario, ofertas y puntos (salvo que las líneas ya traigan su descuento)
    manuales = any("descuento" in linea for linea in lineas)
    cot = None if manuales else cotizar(negocio, lineas, cliente_ref, puntos_canjear, timezone.localdate(fecha),
                                        descuento_general_pct=descuento_general_pct, momento=fecha)
    if cot:
        lineas = cot["lineas"]
    venta = Venta.objects.create(
        negocio=negocio, vendedor=vendedor, fecha=fecha, cliente=cliente or (cliente_ref.nombre if cliente_ref else ""),
        medio_pago=medio_pago, cliente_ref=cliente_ref, oferta=cot["oferta"] if cot else None,
        puntos_canjeados=cot["puntos_canjeados"] if cot else 0, descuento_puntos=cot["descuento_puntos"] if cot else 0,
        propina=Decimal(str(propina or 0)),
    )
    for producto, falta in faltantes:
        _ajuste_venta_sin_stock(producto, falta, vendedor, fecha, venta)

    total = Decimal("0")
    for linea in lineas:
        producto = linea["producto"]
        detalle = DetalleVenta.objects.create(
            venta=venta,
            producto=producto,
            cantidad=Decimal(str(linea["cantidad"])),
            precio_unitario=Decimal(str(linea.get("precio_unitario", producto.precio_venta))),
            costo_unitario=costo_receta(producto) if producto.es_preparado else producto.precio_compra,
            descuento=Decimal(str(linea.get("descuento", 0))),
            oferta=linea.get("oferta"),
            promocion=linea.get("promocion", ""),
        )
        total += detalle.subtotal
        if producto.es_preparado:  # el plato no tiene stock, pero su demanda sirve para analizar las ventas
            from apps.analitica.services import acumular_demanda_diaria

            acumular_demanda_diaria(producto, timezone.localdate(fecha), detalle.cantidad)
    for producto, cantidad, tipo in sorted(salidas.values(), key=lambda f: f[0].pk):  # orden fijo de bloqueo
        registrar_movimiento(
            producto=producto, tipo=tipo, cantidad=cantidad, usuario=vendedor, fecha=fecha,
            motivo=f"Venta #{venta.pk}", referencia_tipo="venta", referencia_id=venta.pk,
            evaluar_alertas=evaluar_alertas,
        )
    venta.total = total
    venta.puntos_ganados = puntos_por_compra(negocio, cliente_ref, total)
    venta.pagado_con_credito = min(Decimal(str(pagado_con_credito or 0)), total)
    venta.save(update_fields=["total", "puntos_ganados", "pagado_con_credito"])
    registrar_compra(venta)
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
    """Revierte el inventario (devolución de cliente), descuenta la demanda registrada y los puntos."""
    from apps.analitica.services import acumular_demanda_diaria
    from apps.clientes.services import revertir_compra
    from apps.core.auditoria import auditar

    if venta.estado == Venta.Estado.ANULADA:
        raise ValueError("La venta ya está anulada.")
    if not motivo.strip():
        raise ValueError("Indica el motivo de la anulación.")
    dia = timezone.localdate(venta.fecha)
    for d in venta.detalles.select_related("producto"):
        acumular_demanda_diaria(d.producto, dia, -d.cantidad)
    # Vuelve lo que salió del inventario con esta venta (productos e insumos de las recetas)
    for producto, cantidad, tipo in salidas_de_venta(venta):
        registrar_movimiento(
            producto=producto, tipo=TipoMovimiento.ENTRADA_DEVOLUCION_CLIENTE, cantidad=cantidad, usuario=usuario,
            motivo=f"Anulación venta #{venta.pk}: {motivo}", referencia_tipo="venta", referencia_id=venta.pk,
            fecha=fecha,
        )
        if tipo == TipoMovimiento.SALIDA_INSUMO:
            acumular_demanda_diaria(producto, dia, -cantidad)
    venta.estado = Venta.Estado.ANULADA
    venta.save(update_fields=["estado"])
    revertir_compra(venta, usuario)
    auditar(venta.negocio, usuario, "anular_venta", venta, motivo=motivo, total=str(venta.total))
    return venta


def salidas_de_venta(venta: Venta) -> list[tuple]:
    """(producto, cantidad, tipo) que salieron del inventario con la venta, uno por producto (los lotes se suman)."""
    from apps.inventario.models import Movimiento

    agrupadas: dict[int, list] = {}
    for m in Movimiento.objects.filter(referencia_tipo="venta", referencia_id=venta.pk, negocio=venta.negocio,
                                       tipo__in=[TipoMovimiento.SALIDA_VENTA, TipoMovimiento.SALIDA_INSUMO]
                                       ).select_related("producto").order_by("producto_id"):
        fila = agrupadas.setdefault(m.producto_id, [m.producto, Decimal("0"), m.tipo])
        fila[1] += m.cantidad
    return [tuple(f) for f in agrupadas.values()]
