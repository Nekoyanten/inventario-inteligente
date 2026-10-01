"""Reglas de bares y discotecas: cuentas abiertas, cover y aforo, reservas y grupos, botellas y tragos.

Las ventas siempre terminan en ventas.services.registrar_venta (inventario, ofertas, puntos y reportes quedan
consistentes con el resto del sistema)."""

from datetime import timedelta
from decimal import ROUND_DOWN, Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.catalogo.models import Categoria, Producto, TipoProducto, UnidadMedida
from apps.core.auditoria import auditar

from .models import (
    AsignacionMesa,
    BotellaGuardada,
    ConfiguracionNocturna,
    Cuenta,
    EntregaMesero,
    Ingreso,
    Invitado,
    ItemCuenta,
    Mesa,
    Reserva,
    noche_de,
)


class ErrorNocturno(Exception):
    pass


def configuracion(negocio) -> ConfiguracionNocturna:
    conf = getattr(negocio, "nocturno", None)
    if conf is None:
        conf, _ = ConfiguracionNocturna.objects.get_or_create(
            negocio=negocio, defaults=ConfiguracionNocturna.valores_para(negocio.giro))
    return conf


def _producto_sistema(negocio, sku, nombre, precio=0) -> Producto:
    """Productos que usa el sistema para el cover y el consumo mínimo (preparados sin receta: no tienen stock)."""
    cat, _ = Categoria.objects.get_or_create(negocio=negocio, nombre="Entradas y cover")
    p, _ = Producto.objects.get_or_create(negocio=negocio, sku=sku, defaults={
        "nombre": nombre, "tipo": TipoProducto.PREPARADO, "categoria": cat, "precio_venta": precio})
    return p


# ---------------------------------------------------------------- cuentas
@transaction.atomic
def abrir_cuenta(negocio, usuario, *, mesa: Mesa | None = None, nombre="", cliente=None, personas=1, reserva=None,
                 momento=None, mesero=None) -> Cuenta:
    momento = momento or timezone.now()
    if mesa is not None and Cuenta.objects.filter(mesa=mesa, estado=Cuenta.Estado.ABIERTA).exists():
        raise ErrorNocturno(f"La mesa {mesa} ya tiene una cuenta abierta.")
    conf = configuracion(negocio)
    noche = noche_de(momento, negocio)
    if mesero is None:
        mesero = mesero_de(mesa, noche) if mesa is not None else None
        if mesero is None and getattr(usuario, "rol", "") == "MESERO":
            mesero = usuario
    cuenta = Cuenta.objects.create(
        negocio=negocio, mesa=mesa, nombre=nombre[:80], cliente=cliente or (reserva.cliente if reserva else None),
        personas=max(1, int(personas or 1)), reserva=reserva, abierta_por=usuario, noche=noche, mesero=mesero,
        consumo_minimo=(reserva.consumo_minimo if reserva and reserva.consumo_minimo else (mesa.consumo_minimo if mesa
                                                                                          else 0)),
        credito=reserva.anticipo if reserva else 0,
        descuento_grupo_pct=conf.grupo_descuento_pct if reserva and reserva.es_grupo else 0,
    )
    Cuenta.objects.filter(pk=cuenta.pk).update(creado=momento)
    auditar(negocio, usuario, "abrir_cuenta", cuenta, mesa=getattr(mesa, "pk", None))
    return cuenta


# ---------------------------------------------------------------- mesas y meseros
def orden_natural(mesas):
    """M1, M2 … M10 (no M1, M10, M2): por zona y luego por el número del nombre."""
    import re

    def clave(m):
        return (m.zona, [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", m.nombre)])

    return sorted(mesas, key=clave)


def mesero_de(mesa: Mesa, noche):
    a = AsignacionMesa.objects.filter(mesa=mesa, noche=noche).select_related("mesero").first()
    return a.mesero if a else None


def mesas_de(negocio, mesero, noche):
    return Mesa.objects.filter(negocio=negocio, activa=True, asignaciones__noche=noche, asignaciones__mesero=mesero)


def asignar_mesas(negocio, noche, asignacion: dict, usuario) -> int:
    """asignacion: {mesa_id: mesero (Usuario) o None}. Devuelve cuántas mesas quedaron con mesero."""
    with transaction.atomic():
        for mesa_id, mesero in asignacion.items():
            if mesero is None:
                AsignacionMesa.objects.filter(negocio=negocio, noche=noche, mesa_id=mesa_id).delete()
            else:
                AsignacionMesa.objects.update_or_create(negocio=negocio, noche=noche, mesa_id=mesa_id,
                                                        defaults={"mesero": mesero})
        # las cuentas abiertas de esas mesas pasan al nuevo mesero
        for a in AsignacionMesa.objects.filter(negocio=negocio, noche=noche):
            Cuenta.objects.filter(mesa_id=a.mesa_id, estado=Cuenta.Estado.ABIERTA).exclude(
                mesero=a.mesero).update(mesero=a.mesero)
    total = AsignacionMesa.objects.filter(negocio=negocio, noche=noche).count()
    auditar(negocio, usuario, "asignar_mesas", negocio, noche=str(noche), mesas=total)
    return total


def copiar_asignacion(negocio, noche, usuario) -> int:
    """Repite la asignación de la última noche que tuvo (solo meseros que siguen activos)."""
    anterior = (AsignacionMesa.objects.filter(negocio=negocio, noche__lt=noche).order_by("-noche")
                .values_list("noche", flat=True).first())
    if anterior is None:
        raise ErrorNocturno("Todavía no hay una noche anterior con mesas asignadas.")
    previas = AsignacionMesa.objects.filter(negocio=negocio, noche=anterior, mesero__is_active=True,
                                            mesa__activa=True).select_related("mesero")
    return asignar_mesas(negocio, noche, {a.mesa_id: a.mesero for a in previas}, usuario)


def repartir_mesas(negocio, noche, meseros, usuario) -> int:
    """Reparte las mesas activas entre los meseros, por zonas seguidas (cada uno queda con mesas vecinas)."""
    meseros = list(meseros)
    if not meseros:
        raise ErrorNocturno("Primero crea usuarios con el rol Mesero (en Equipo).")
    mesas = orden_natural(Mesa.objects.filter(negocio=negocio, activa=True))
    if not mesas:
        raise ErrorNocturno("Primero crea las mesas.")
    por_mesero = -(-len(mesas) // len(meseros))  # redondeo hacia arriba
    return asignar_mesas(negocio, noche, {m.pk: meseros[i // por_mesero] for i, m in enumerate(mesas)}, usuario)


def puede_atender(usuario, cuenta: Cuenta) -> bool:
    """El cajero y el dueño ven todas las cuentas; el mesero, solo las de sus mesas."""
    if usuario.puede("cobrar_cuentas") or usuario.puede("asignar_mesas"):
        return True
    if not usuario.puede("atender_mesas"):
        return False
    if cuenta.mesero_id == usuario.pk or (cuenta.mesero_id is None and cuenta.abierta_por_id == usuario.pk):
        return True
    return bool(cuenta.mesa_id and AsignacionMesa.objects.filter(mesa_id=cuenta.mesa_id, noche=cuenta.noche,
                                                                 mesero=usuario).exists())


def quien_tiene(mesa: Mesa, noche):
    """(cuenta abierta, mesero asignado) de la mesa esta noche."""
    abierta = Cuenta.objects.filter(mesa=mesa, estado=Cuenta.Estado.ABIERTA).select_related("mesero").first()
    return abierta, mesero_de(mesa, noche)


def tomar_mesa(negocio, mesero, mesa: Mesa, personas=2) -> Cuenta:
    """El mesero toca una mesa libre en el tablero y queda a su cargo hasta que se cobre o se libere."""
    noche = noche_de(timezone.now(), negocio)
    abierta, asignado = quien_tiene(mesa, noche)
    if abierta is not None:
        quien = (abierta.mesero.get_full_name() or abierta.mesero.username) if abierta.mesero else "otra persona"
        raise ErrorNocturno(f"La mesa {mesa} ya la está atendiendo {quien}.")
    if asignado is not None and asignado.pk != mesero.pk:
        raise ErrorNocturno(f"La mesa {mesa} está asignada a {asignado.get_full_name() or asignado.username} esta noche.")
    return abrir_cuenta(negocio, mesero, mesa=mesa, personas=personas, mesero=mesero)


def liberar_mesa(cuenta: Cuenta, usuario):
    """La gente se fue sin pedir nada: la mesa vuelve a quedar libre (si hay pedidos, primero se cobra)."""
    _validar_abierta(cuenta)
    if cuenta.items.exists():
        raise ErrorNocturno("Esta mesa tiene pedidos: cóbrala para dejarla libre.")
    cuenta.estado, cuenta.cerrada = Cuenta.Estado.ANULADA, timezone.now()
    cuenta.save(update_fields=["estado", "cerrada", "actualizado"])
    auditar(cuenta.negocio, usuario, "liberar_mesa", cuenta)


def registrar_entrega(cuenta: Cuenta, venta, mesero, paga_con=0) -> EntregaMesero | None:
    """Cuando el mesero cobra en efectivo, la caja queda esperando esa plata (y sabe cuántas vueltas se dieron)."""
    if venta.medio_pago != "EFECTIVO":
        return None
    valor = venta.total - venta.pagado_con_credito + venta.propina
    if valor <= 0:
        return None
    paga_con = Decimal(str(paga_con or 0))
    vueltas = max(Decimal("0"), paga_con - valor) if paga_con else Decimal("0")
    return EntregaMesero.objects.create(negocio=cuenta.negocio, mesero=mesero, cuenta=cuenta, venta=venta,
                                        valor=valor, paga_con=paga_con if paga_con else valor, vueltas=vueltas)


def recibir_entrega(entrega: EntregaMesero, usuario):
    if entrega.recibida is None:
        entrega.recibida, entrega.recibida_por = timezone.now(), usuario
        entrega.save(update_fields=["recibida", "recibida_por"])
        auditar(entrega.negocio, usuario, "recibir_entrega", entrega.cuenta, valor=str(entrega.valor),
                mesero=entrega.mesero.username)


def pedir_la_cuenta(cuenta: Cuenta, usuario):
    _validar_abierta(cuenta)
    if not cuenta.items.filter(venta__isnull=True).exists():
        raise ErrorNocturno("La cuenta no tiene pedidos por cobrar.")
    cuenta.pide_cuenta = timezone.now()
    cuenta.save(update_fields=["pide_cuenta", "actualizado"])
    auditar(cuenta.negocio, usuario, "pedir_cuenta", cuenta)


def _validar_abierta(cuenta: Cuenta):
    if cuenta.estado != Cuenta.Estado.ABIERTA:
        raise ErrorNocturno("La cuenta ya está cerrada.")


def agregar_item(cuenta: Cuenta, producto: Producto, cantidad, usuario, *, momento=None, cortesia=False,
                 nota="") -> ItemCuenta:
    _validar_abierta(cuenta)
    cantidad = Decimal(str(cantidad))
    if cantidad <= 0:
        raise ErrorNocturno("La cantidad debe ser mayor que cero.")
    if producto.negocio_id != cuenta.negocio_id or not producto.vendible:
        raise ErrorNocturno(f"{producto.nombre} no se puede vender.")
    item = ItemCuenta.objects.create(cuenta=cuenta, producto=producto, cantidad=cantidad,
                                     agregado=momento or timezone.now(), agregado_por=usuario, cortesia=cortesia,
                                     nota=nota[:120])
    if cortesia:  # las cortesías quedan en la bitácora (quién invitó qué)
        auditar(cuenta.negocio, usuario, "cortesia", cuenta, producto=producto.pk, cantidad=str(cantidad))
    return item


def quitar_item(item: ItemCuenta, usuario, motivo: str):
    _validar_abierta(item.cuenta)
    if item.venta_id:
        raise ErrorNocturno("Ese pedido ya se cobró.")
    if not motivo.strip():
        raise ErrorNocturno("Escribe por qué se quita (queda en la bitácora).")
    auditar(item.cuenta.negocio, usuario, "quitar_pedido", item.cuenta, producto=item.producto_id,
            cantidad=str(item.cantidad), motivo=motivo)
    item.delete()


def _lineas(items):
    return [{"producto": i.producto, "cantidad": i.cantidad, "momento": i.agregado, "cortesia": i.cortesia,
             "item_id": i.pk} for i in items]


def resumen(cuenta: Cuenta, items=None, puntos=0) -> dict:
    """Lo que se debe: descuentos (happy hour, grupo, ofertas), crédito del cover o anticipo, mínimo y propina."""
    from apps.clientes.services import cotizar

    items = list(items if items is not None else cuenta.items.filter(venta__isnull=True).select_related("producto"))
    if not items:
        return {"items": [], "subtotal": Decimal("0"), "total": Decimal("0"), "credito": cuenta.credito_disponible,
                "a_pagar": Decimal("0"), "faltante_minimo": Decimal("0"), "propina_sugerida": Decimal("0"),
                "por_persona": Decimal("0"), "lineas": [], "puntos_ganados": 0, "descuento": Decimal("0")}
    cot = cotizar(cuenta.negocio, _lineas(items), cuenta.cliente, puntos, descuento_general_pct=cuenta.descuento_grupo_pct)
    for linea in cot["lineas"]:
        linea["bruto"] = Decimal(str(linea["cantidad"])) * linea["precio_unitario"]
        linea["neto"] = linea["bruto"] - linea["descuento"]
    consumido = cot["total"] + _cobrado(cuenta)
    faltante = max(Decimal("0"), cuenta.consumo_minimo - consumido) if cuenta.consumo_minimo else Decimal("0")
    total = cot["total"] + faltante
    credito = min(cuenta.credito_disponible, total)
    conf = configuracion(cuenta.negocio)
    return {
        "items": items, "lineas": cot["lineas"], "subtotal": sum(i.cantidad * i.producto.precio_venta for i in items),
        "descuento": sum(linea["descuento"] for linea in cot["lineas"]), "total": total, "credito": credito,
        "a_pagar": total - credito, "faltante_minimo": faltante,
        "propina_sugerida": (cot["total"] * min(conf.propina_sugerida_pct, 10) / 10000).quantize(
            Decimal("1"), rounding=ROUND_DOWN) * 100,  # a centenas, hacia abajo: nunca pasa del 10 %
        "por_persona": ((total - credito) / cuenta.personas).quantize(Decimal("1")) if cuenta.personas else total,
        "puntos_ganados": cot["puntos_ganados"],
    }


def _cobrado(cuenta: Cuenta) -> Decimal:
    from apps.ventas.models import Venta

    ids = cuenta.items.filter(venta__isnull=False).values_list("venta", flat=True).distinct()
    return Venta.objects.filter(pk__in=list(ids), estado=Venta.Estado.COMPLETADA).aggregate(t=Sum("total"))["t"] or 0


@transaction.atomic
def cobrar(cuenta: Cuenta, usuario, *, items_ids=None, medio_pago="EFECTIVO", propina=0, puntos=0, fecha=None):
    """Cobra la cuenta completa o solo algunos pedidos (dividir la cuenta). Devuelve la venta.

    Al cobrar lo último: se completa el consumo mínimo si no se alcanzó, el cover consumible que no se usó queda
    como ingreso y el organizador de un grupo gana sus puntos."""
    from apps.ventas.services import registrar_venta

    cuenta = Cuenta.objects.select_for_update().get(pk=cuenta.pk)
    _validar_abierta(cuenta)
    pendientes = cuenta.items.filter(venta__isnull=True).select_related("producto")
    items = list(pendientes.filter(pk__in=items_ids) if items_ids else pendientes)
    if not items:
        raise ErrorNocturno("No hay pedidos por cobrar.")
    ultimo = len(items) == pendientes.count()
    lineas = _lineas(items)
    r = resumen(cuenta, items, puntos) if ultimo else None
    if ultimo and r["faltante_minimo"] > 0:
        lineas.append({"producto": _producto_sistema(cuenta.negocio, "CONSUMO-MIN", "Consumo mínimo (diferencia)"),
                       "cantidad": 1, "precio_unitario": r["faltante_minimo"], "sin_descuento": True})
    fecha = fecha or timezone.now()
    venta = registrar_venta(negocio=cuenta.negocio, vendedor=usuario, lineas=lineas, medio_pago=medio_pago,
                            fecha=fecha, cliente_ref=cuenta.cliente, puntos_canjear=puntos,
                            descuento_general_pct=cuenta.descuento_grupo_pct, propina=propina,
                            pagado_con_credito=cuenta.credito_disponible)
    ItemCuenta.objects.filter(pk__in=[i.pk for i in items]).update(venta=venta)
    usado = venta.pagado_con_credito
    cuenta.credito_usado += usado
    if ultimo:
        sobrante = cuenta.credito - cuenta.credito_usado
        if sobrante > 0 and cuenta.ingresos.filter(consumible=True).exists():
            # cover consumible que no se consumió: no se devuelve, es ingreso de la noche
            registrar_venta(negocio=cuenta.negocio, vendedor=usuario, fecha=fecha, pagado_con_credito=sobrante,
                            lineas=[{"producto": _producto_sistema(cuenta.negocio, "COVER", "Cover / entrada"),
                                     "cantidad": 1, "precio_unitario": sobrante, "sin_descuento": True}])
            cuenta.credito_usado += sobrante
        cuenta.estado, cuenta.cerrada = Cuenta.Estado.COBRADA, fecha
        _bono_grupo(cuenta, usuario, venta)
    cuenta.pide_cuenta = None
    cuenta.save()
    auditar(cuenta.negocio, usuario, "cobrar_cuenta", cuenta, venta=venta.pk, total=str(venta.total),
            completa=ultimo)
    return venta


def _bono_grupo(cuenta: Cuenta, usuario, venta):
    """El que organiza un grupo grande gana puntos por cada persona que llegó (fidelización por grupos)."""
    from apps.clientes.models import MovimientoPuntos
    from apps.clientes.services import _asentar

    reserva = cuenta.reserva
    if not (reserva and reserva.cliente_id and reserva.es_grupo):
        return
    marca = f"Grupo reserva #{reserva.pk}"
    if MovimientoPuntos.objects.filter(cliente=reserva.cliente, motivo__startswith=marca).exists():
        return
    conf = configuracion(cuenta.negocio)
    asistentes = reserva.llegaron or cuenta.personas
    puntos = asistentes * conf.grupo_puntos_por_asistente
    if puntos:
        _asentar(reserva.cliente, MovimientoPuntos.Tipo.BONO, puntos, venta=venta, usuario=usuario,
                 motivo=f"{marca}: {asistentes} personas")


def anular_cuenta(cuenta: Cuenta, usuario, motivo: str):
    _validar_abierta(cuenta)
    if cuenta.items.filter(venta__isnull=False).exists():
        raise ErrorNocturno("Ya se cobró una parte: anula esas ventas desde su comprobante.")
    if not motivo.strip():
        raise ErrorNocturno("Escribe el motivo.")
    cuenta.estado, cuenta.cerrada = Cuenta.Estado.ANULADA, timezone.now()
    cuenta.save(update_fields=["estado", "cerrada", "actualizado"])
    auditar(cuenta.negocio, usuario, "anular_cuenta", cuenta, motivo=motivo, pedidos=cuenta.items.count())


# ---------------------------------------------------------------- cover y aforo
def presentes(negocio, noche) -> int:
    return Ingreso.objects.filter(negocio=negocio, noche=noche).aggregate(p=Sum("personas"))["p"] or 0


def cover_para(negocio, cliente=None, reserva=None) -> tuple[Decimal, str, int]:
    """(valor por persona, motivo del beneficio, cuántas personas entran gratis) según el cliente que llega.

    El beneficio es para el cliente (y sus acompañantes gratis si es VIP o frecuente), no para todo su grupo."""
    conf = configuracion(negocio)
    if not conf.cover_valor:
        return Decimal("0"), "", 0
    valor = Decimal(conf.cover_valor)
    if cliente is not None:
        if conf.cover_gratis_desde == "VIP" and cliente.nivel == "VIP":
            return valor, "Cliente VIP", 1 + conf.acompanantes_gratis
        if conf.cover_gratis_desde == "FRECUENTE" and cliente.nivel in ("VIP", "FRECUENTE"):
            return valor, f"Cliente {cliente.get_nivel_display().lower()}", 1 + conf.acompanantes_gratis
        hoy = timezone.localdate()
        if cliente.fecha_nacimiento and cliente.fecha_nacimiento.month == hoy.month and reserva and \
                reserva.tipo == Reserva.Tipo.CUMPLEANOS:
            return valor, "Cumpleañero", 1
    return valor, "", 0


@transaction.atomic
def registrar_ingreso(negocio, usuario, *, personas=1, cliente=None, reserva=None, cuenta=None, medio_pago="EFECTIVO",
                      momento=None) -> Ingreso:
    """Entrada por la puerta: controla el aforo y cobra el cover (consumible = queda como saldo en la cuenta)."""
    momento = momento or timezone.now()
    conf = configuracion(negocio)
    noche = noche_de(momento, negocio)
    personas = max(1, int(personas))
    if conf.aforo and presentes(negocio, noche) + personas > conf.aforo:
        raise ErrorNocturno(f"Aforo completo ({conf.aforo} personas).")
    valor, motivo, gratis = cover_para(negocio, cliente, reserva)
    ingreso = Ingreso.objects.create(negocio=negocio, noche=noche, fecha=momento, personas=personas,
                                     valor_por_persona=valor, personas_gratis=min(gratis, personas),
                                     consumible=conf.cover_consumible, cliente=cliente,
                                     reserva=reserva, motivo_gratis=motivo, medio_pago=medio_pago, usuario=usuario)
    total = ingreso.total
    if total and conf.cover_consumible:
        if cuenta is None:
            nombre = f"Cover · {cliente.nombre if cliente else f'entrada #{ingreso.pk}'}"
            cuenta = abrir_cuenta(negocio, usuario, nombre=nombre, cliente=cliente, personas=personas, momento=momento)
        Cuenta.objects.filter(pk=cuenta.pk).update(credito=cuenta.credito + total)
        cuenta.refresh_from_db()
        ingreso.cuenta = cuenta
    elif total:
        from apps.ventas.services import registrar_venta

        ingreso.venta = registrar_venta(
            negocio=negocio, vendedor=usuario, fecha=momento, medio_pago=medio_pago, cliente_ref=cliente,
            lineas=[{"producto": _producto_sistema(negocio, "COVER", "Cover / entrada", valor),
                     "cantidad": personas - ingreso.personas_gratis,
                     "precio_unitario": valor, "sin_descuento": True}])
    ingreso.save()
    return ingreso


# ---------------------------------------------------------------- reservas, grupos y listas
def marcar_llegada(reserva: Reserva, usuario, *, mesa=None, momento=None) -> Cuenta:
    if reserva.estado in (Reserva.Estado.CANCELADA, Reserva.Estado.LLEGO):
        raise ErrorNocturno("La reserva no está pendiente.")
    reserva.estado = Reserva.Estado.LLEGO
    if mesa is not None:
        reserva.mesa = mesa
    reserva.save(update_fields=["estado", "mesa", "actualizado"])
    return abrir_cuenta(reserva.negocio, usuario, mesa=reserva.mesa, nombre=f"Reserva · {reserva.nombre}",
                        personas=reserva.personas, reserva=reserva, momento=momento)


def llegada_invitado(invitado: Invitado, usuario, *, registrar_cliente=False, acepta_ofertas=False,
                     mayor_edad=False) -> Invitado:
    """El invitado llega. Si autoriza, queda registrado como cliente (referido por quien organizó)."""
    from apps.clientes.models import Cliente
    from apps.clientes.services import normalizar_telefono

    invitado.llego, invitado.llegada = True, timezone.now()
    if registrar_cliente and invitado.telefono:
        reserva = invitado.reserva
        conf = configuracion(reserva.negocio)
        if conf.exigir_mayoria_edad and not mayor_edad:
            raise ErrorNocturno("Verifica con la cédula que es mayor de edad antes de registrarlo.")
        tel = normalizar_telefono(invitado.telefono)
        cliente, creado = Cliente.objects.get_or_create(negocio=reserva.negocio, telefono=tel, defaults={
            "nombre": invitado.nombre, "acepta_datos": True, "acepta_ofertas": acepta_ofertas,
            "fecha_autorizacion": timezone.now(), "mayor_edad_verificado": mayor_edad,
            "referido_por": reserva.cliente})
        invitado.cliente = cliente
    invitado.save()
    return invitado


def reservas_vencidas(negocio, hoy=None) -> int:
    """Reservas de noches pasadas que nadie marcó: quedan como «no llegó» (para medir la tasa de no show)."""
    hoy = hoy or noche_de(timezone.now(), negocio)
    return Reserva.objects.filter(negocio=negocio, fecha__lt=hoy,
                                  estado__in=[Reserva.Estado.PENDIENTE, Reserva.Estado.CONFIRMADA]
                                  ).update(estado=Reserva.Estado.NO_LLEGO)


# ---------------------------------------------------------------- botellas y tragos
def crear_trago(botella: Producto, *, ml_botella: int, ml_trago: int, precio, nombre="", usuario=None) -> Producto:
    """«Vender por tragos»: crea el trago como preparado cuya receta gasta ml_trago/ml_botella de la botella."""
    from apps.inventario.recetas import guardar_item_receta

    if botella.es_preparado or botella.es_agrupador:
        raise ErrorNocturno("Elige una botella con stock.")
    if not (0 < ml_trago < ml_botella):
        raise ErrorNocturno("Revisa los mililitros: el trago debe ser menor que la botella.")
    unidad = UnidadMedida.objects.filter(abreviatura="bot").first()
    if unidad and botella.unidad_id != unidad.pk:
        Producto.objects.filter(pk=botella.pk).update(unidad=unidad)  # permite stock en fracciones (botella abierta)
        botella.unidad = unidad
    cat, _ = Categoria.objects.get_or_create(negocio=botella.negocio, nombre="Tragos y cócteles")
    sku = f"{botella.sku}-T{ml_trago}"[:40]
    trago, _ = Producto.objects.update_or_create(negocio=botella.negocio, sku=sku, defaults={
        "nombre": nombre or f"Trago de {botella.nombre} ({ml_trago} ml)", "tipo": TipoProducto.PREPARADO,
        "categoria": cat, "precio_venta": Decimal(str(precio)), "activo": True})
    guardar_item_receta(trago, botella, Decimal(ml_trago) / Decimal(ml_botella), usuario=usuario)
    return trago


def guardar_botella(cliente, producto: Producto, restante_pct: int, usuario, ubicacion="") -> BotellaGuardada:
    if not (0 < int(restante_pct) < 100):
        raise ErrorNocturno("Indica cuánto quedó (entre 1 y 99 %).")
    conf = configuracion(cliente.negocio)
    return BotellaGuardada.objects.create(
        negocio=cliente.negocio, cliente=cliente, producto=producto, restante_pct=int(restante_pct),
        vence=timezone.localdate() + timedelta(days=conf.botella_guardada_dias), ubicacion=ubicacion[:40],
        usuario=usuario)


def retirar_botella(botella: BotellaGuardada, usuario) -> BotellaGuardada:
    if botella.estado != BotellaGuardada.Estado.GUARDADA:
        raise ErrorNocturno("Esa botella ya no está guardada.")
    botella.estado, botella.retirada = BotellaGuardada.Estado.RETIRADA, timezone.now()
    botella.save(update_fields=["estado", "retirada"])
    auditar(botella.negocio, usuario, "retirar_botella", botella, cliente=botella.cliente_id)
    return botella


def vencer_botellas(negocio, hoy=None) -> int:
    hoy = hoy or timezone.localdate()
    return BotellaGuardada.objects.filter(negocio=negocio, estado=BotellaGuardada.Estado.GUARDADA,
                                          vence__lt=hoy).update(estado=BotellaGuardada.Estado.VENCIDA)
