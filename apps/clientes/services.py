"""Reglas de fidelización: puntos, niveles, ofertas y mensajes de WhatsApp."""

import math
import re
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal
from urllib.parse import quote

from django.db import transaction
from django.db.models import Count, Sum
from django.utils import timezone

from apps.core.auditoria import auditar

from .models import MULTIPLICADOR_NIVEL, Cliente, EnvioOferta, MovimientoPuntos, Nivel, Oferta, Segmento


class ErrorClientes(Exception):
    pass


def normalizar_telefono(texto: str) -> str:
    """'+57 300 123 4567' → '3001234567'. Deja solo dígitos; quita el indicativo de Colombia si viene."""
    digitos = re.sub(r"\D", "", texto or "")
    if len(digitos) == 12 and digitos.startswith("57"):
        digitos = digitos[2:]
    return digitos[:20]


def url_whatsapp(telefono: str, texto: str) -> str:
    numero = normalizar_telefono(telefono)
    if len(numero) == 10:
        numero = "57" + numero
    return f"https://wa.me/{numero}?text={quote(texto)}"


def _config(negocio):
    return getattr(negocio, "config", None)


# ---------------------------------------------------------------- puntos
def _asentar(cliente: Cliente, tipo, puntos: int, *, venta=None, usuario=None, motivo="", fecha=None) -> MovimientoPuntos:
    cliente = Cliente.objects.select_for_update().get(pk=cliente.pk)
    saldo = cliente.puntos + puntos
    if saldo < 0:
        raise ErrorClientes(f"{cliente.nombre} tiene {cliente.puntos} puntos; no alcanzan.")
    mov = MovimientoPuntos.objects.create(cliente=cliente, venta=venta, tipo=tipo, puntos=puntos, saldo=saldo,
                                          fecha=fecha or timezone.now(), usuario=usuario, motivo=motivo[:200])
    Cliente.objects.filter(pk=cliente.pk).update(puntos=saldo)
    return mov


def puntos_por_compra(negocio, cliente: Cliente | None, total) -> int:
    config = _config(negocio)
    if not (cliente and config and config.fidelizacion_activa and config.pesos_por_punto):
        return 0
    base = Decimal(str(total)) / config.pesos_por_punto
    return math.floor(base * Decimal(str(MULTIPLICADOR_NIVEL.get(cliente.nivel, 1))))


def valor_puntos(negocio, puntos: int) -> Decimal:
    config = _config(negocio)
    return Decimal(puntos * (config.valor_punto if config else 0))


def validar_canje(negocio, cliente: Cliente | None, puntos: int) -> int:
    if not puntos:
        return 0
    config = _config(negocio)
    if not (cliente and config and config.fidelizacion_activa):
        raise ErrorClientes("Para canjear puntos, identifica al cliente.")
    if puntos < config.puntos_minimos_canje:
        raise ErrorClientes(f"Se canjean desde {config.puntos_minimos_canje} puntos.")
    if puntos > cliente.puntos:
        raise ErrorClientes(f"{cliente.nombre} tiene {cliente.puntos} puntos.")
    return puntos


@transaction.atomic
def registrar_compra(venta) -> None:
    """Tras una venta con cliente: canje (si lo hubo), puntos ganados, estadísticas y nivel."""
    cliente = venta.cliente_ref
    if cliente is None:
        return
    if venta.puntos_canjeados:
        _asentar(cliente, MovimientoPuntos.Tipo.CANJEADOS, -venta.puntos_canjeados, venta=venta, usuario=venta.vendedor,
                 motivo=f"Descuento en venta #{venta.pk}", fecha=venta.fecha)
    if venta.puntos_ganados:
        _asentar(cliente, MovimientoPuntos.Tipo.GANADOS, venta.puntos_ganados, venta=venta, usuario=venta.vendedor,
                 motivo=f"Venta #{venta.pk}", fecha=venta.fecha)
    cliente = recalcular(cliente, venta.fecha)
    if getattr(venta.negocio, "giro", "") in ("BAR", "DISCOTECA", "BAR_DISCOTECA"):
        from apps.nocturno.fidelizacion import bonos_por_compra

        bonos_por_compra(venta, cliente)


@transaction.atomic
def revertir_compra(venta, usuario) -> None:
    """Anulación: se devuelven los puntos canjeados y se quitan los ganados (sin dejar el saldo negativo)."""
    cliente = venta.cliente_ref
    if cliente is None:
        return
    cliente.refresh_from_db()
    bonos = MovimientoPuntos.objects.filter(venta=venta, tipo=MovimientoPuntos.Tipo.BONO).aggregate(
        t=Sum("puntos"))["t"] or 0
    ajuste = venta.puntos_canjeados - min(venta.puntos_ganados + bonos, cliente.puntos + venta.puntos_canjeados)
    if ajuste:
        _asentar(cliente, MovimientoPuntos.Tipo.DEVUELTOS, ajuste, venta=venta, usuario=usuario,
                 motivo=f"Anulación de la venta #{venta.pk}")
    recalcular(cliente)


def ajustar_puntos(cliente: Cliente, puntos: int, usuario, motivo: str) -> MovimientoPuntos:
    if not motivo.strip():
        raise ErrorClientes("Escribe el motivo del ajuste.")
    with transaction.atomic():
        mov = _asentar(cliente, MovimientoPuntos.Tipo.AJUSTE, puntos, usuario=usuario, motivo=motivo)
    auditar(cliente.negocio, usuario, "ajustar_puntos", cliente, puntos=puntos, motivo=motivo)
    return mov


def recalcular(cliente: Cliente, hoy=None) -> Cliente:
    """Estadísticas y nivel a partir de sus ventas completadas."""
    from apps.ventas.models import Venta

    ahora = hoy or timezone.now()
    ventas = Venta.objects.filter(cliente_ref=cliente, estado=Venta.Estado.COMPLETADA)
    total = ventas.aggregate(n=Count("id"), t=Sum("total"))
    recientes = ventas.filter(fecha__gte=ahora - timedelta(days=90)).aggregate(n=Count("id"), t=Sum("total"))
    config = _config(cliente.negocio)
    nivel = Nivel.NUEVO
    if config and (recientes["t"] or 0) >= config.nivel_vip_monto:
        nivel = Nivel.VIP
    elif config and (recientes["n"] or 0) >= config.nivel_frecuente_compras:
        nivel = Nivel.FRECUENTE
    fechas = ventas.order_by("fecha").values_list("fecha", flat=True)
    Cliente.objects.filter(pk=cliente.pk).update(
        n_compras=total["n"] or 0, total_compras=total["t"] or 0, nivel=nivel,
        primera_compra=fechas.first(), ultima_compra=ventas.order_by("-fecha").values_list("fecha", flat=True).first())
    cliente.refresh_from_db()
    return cliente


# ---------------------------------------------------------------- ofertas
def ofertas_vigentes(negocio, hoy=None):
    hoy = hoy or timezone.localdate()
    return Oferta.objects.filter(negocio=negocio, activa=True, desde__lte=hoy, hasta__gte=hoy).select_related(
        "producto", "categoria")


def cliente_en_segmento(cliente: Cliente | None, oferta: Oferta, hoy=None) -> bool:
    hoy = hoy or timezone.localdate()
    s = oferta.segmento
    if s == Segmento.TODOS:
        return True
    if cliente is None:
        return False
    if s == Segmento.VIP:
        return cliente.nivel == Nivel.VIP
    if s == Segmento.FRECUENTES:
        return cliente.nivel in (Nivel.FRECUENTE, Nivel.VIP)
    if s == Segmento.NUEVOS:
        return cliente.n_compras <= 1
    if s == Segmento.CUMPLEANOS:
        return bool(cliente.fecha_nacimiento and cliente.fecha_nacimiento.month == hoy.month)
    if s == Segmento.EN_RIESGO:
        from .analisis import segmento_rfm

        return segmento_rfm(cliente, hoy) in ("EN_RIESGO", "PERDIDO")
    if s == Segmento.COMPRADORES:
        return destinatarios(oferta, hoy).filter(pk=cliente.pk).exists() or cliente.ofertas_recibidas.filter(
            oferta=oferta).exists()
    return False


def _aplica_a_producto(oferta: Oferta, producto) -> bool:
    if oferta.producto_id:
        return oferta.producto_id == producto.pk
    if oferta.categoria_id:
        return oferta.categoria_id == producto.categoria_id
    return True


def descuento_maximo_pct(producto) -> Decimal:
    """Nunca vender por debajo del costo: el descuento no puede pasar el margen."""
    if not producto.precio_venta:
        return Decimal("0")
    margen = (producto.precio_venta - producto.precio_compra) / producto.precio_venta * 100
    return max(Decimal("0"), margen.quantize(Decimal("0.01")))


def cotizar(negocio, lineas, cliente: Cliente | None = None, puntos_canjear: int = 0, hoy=None,
            descuento_general_pct=0, momento=None) -> dict:
    """Calcula descuentos, canje de puntos y puntos a ganar. Lo usan la caja (vista previa), las cuentas y la venta.

    lineas: [{"producto": Producto, "cantidad": n, opcionales: "precio_unitario", "momento" (hora del pedido, para
    happy hour), "cortesia" (invitación de la casa), "sin_descuento"}].

    Por línea se aplica UNA sola promoción, en este orden: cortesía → precio especial por horario (happy hour,
    2×1, noche temática) → la mejor entre las ofertas del cliente y el descuento general (p. ej. de grupo).
    Las ofertas y el descuento general nunca dejan el precio por debajo del costo."""
    from apps.core.modulos import activo
    from apps.nocturno.precios import precios_especiales

    momento = momento or timezone.now()
    especiales = precios_especiales(negocio, lineas, momento)
    fidelizacion = activo(negocio, "clientes")  # sin el módulo: el cliente gana puntos, pero no hay ofertas ni canje
    if not fidelizacion:
        puntos_canjear = 0
    ofertas = [o for o in ofertas_vigentes(negocio, hoy) if cliente_en_segmento(cliente, o, hoy)] if fidelizacion else []
    general = Decimal(str(descuento_general_pct or 0))
    resultado, subtotal = [], Decimal("0")
    for linea, especial in zip(lineas, especiales, strict=True):
        p, cant = linea["producto"], Decimal(str(linea["cantidad"]))
        precio = Decimal(str(linea.get("precio_unitario", p.precio_venta)))
        bruto = cant * precio
        mejor, pct, promocion, desc = None, Decimal("0"), "", Decimal("0")
        if linea.get("cortesia"):
            desc, promocion = bruto, "Cortesía de la casa"
        elif not linea.get("sin_descuento"):
            if especial:
                desc, promocion = especial
            else:
                tope = descuento_maximo_pct(p)
                for o in ofertas:
                    if _aplica_a_producto(o, p):
                        candidato = min(o.descuento_pct, tope)
                        if candidato > pct:
                            mejor, pct = o, candidato
                if general and min(general, tope) > pct:
                    mejor, pct = None, min(general, tope)
                    promocion = f"Descuento de grupo {pct_texto(pct)} %"
                desc = (bruto * pct / 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
                if mejor:
                    promocion = mejor.titulo
        desc = min(desc, bruto)
        resultado.append({**linea, "precio_unitario": precio, "descuento": desc, "oferta": mejor, "pct": pct,
                          "promocion": promocion[:80], "_neto": bruto - desc})
        subtotal += bruto - desc
    puntos_canjear = validar_canje(negocio, cliente, int(puntos_canjear or 0))
    desc_puntos = min(valor_puntos(negocio, puntos_canjear), subtotal)
    if puntos_canjear and desc_puntos < valor_puntos(negocio, puntos_canjear):
        config = _config(negocio)
        puntos_canjear = int(desc_puntos // config.valor_punto)  # no se gastan puntos de más
        desc_puntos = valor_puntos(negocio, puntos_canjear)
    # El descuento por puntos se reparte entre las líneas (así los reportes de utilidad quedan bien)
    restante = desc_puntos
    for i, linea in enumerate(resultado):
        neto = linea.pop("_neto")
        parte = restante if i == len(resultado) - 1 else (desc_puntos * neto / subtotal).quantize(Decimal("1")) \
            if subtotal else Decimal("0")
        parte = min(parte, neto, restante)
        linea["descuento"] += parte
        restante -= parte
    total = subtotal - desc_puntos
    ofertas_usadas = [linea["oferta"] for linea in resultado if linea["oferta"]]
    return {
        "lineas": resultado, "subtotal": subtotal, "descuento_ofertas": sum(r["descuento"] for r in resultado) - desc_puntos,
        "puntos_canjeados": puntos_canjear, "descuento_puntos": desc_puntos, "total": total,
        "puntos_ganados": puntos_por_compra(negocio, cliente, total),
        "oferta": max(ofertas_usadas, key=lambda o: o.descuento_pct) if ofertas_usadas else None,
    }


def destinatarios(oferta: Oferta, hoy=None):
    """Clientes a los que se les puede enviar la oferta: del segmento y que aceptaron recibir ofertas."""
    from apps.ventas.models import DetalleVenta

    hoy = hoy or timezone.localdate()
    qs = Cliente.objects.filter(negocio=oferta.negocio, activo=True, acepta_ofertas=True).exclude(telefono="")
    if oferta.negocio.giro == "VAPE":  # Ley 2354: nunca a quien no se le verificó la mayoría de edad
        qs = qs.filter(mayor_edad_verificado=True)
    s = oferta.segmento
    if s == Segmento.VIP:
        qs = qs.filter(nivel=Nivel.VIP)
    elif s == Segmento.FRECUENTES:
        qs = qs.filter(nivel__in=[Nivel.FRECUENTE, Nivel.VIP])
    elif s == Segmento.NUEVOS:
        qs = qs.filter(n_compras__lte=1)
    elif s == Segmento.CUMPLEANOS:
        qs = qs.filter(fecha_nacimiento__month=hoy.month)
    elif s == Segmento.EN_RIESGO:
        from .analisis import clientes_por_segmento

        ids = [c.pk for c in clientes_por_segmento(oferta.negocio, ("EN_RIESGO", "PERDIDO"), hoy)]
        qs = qs.filter(pk__in=ids)
    elif s == Segmento.COMPRADORES:
        filtro = {"producto": oferta.producto} if oferta.producto_id else (
            {"producto__categoria": oferta.categoria} if oferta.categoria_id else {})
        ids = DetalleVenta.objects.filter(venta__negocio=oferta.negocio, venta__cliente_ref__isnull=False, **filtro,
                                          venta__fecha__date__gte=hoy - timedelta(days=180)
                                          ).values_list("venta__cliente_ref", flat=True).distinct()
        qs = qs.filter(pk__in=list(ids))
    return qs.order_by("-total_compras")


def mensaje_oferta(oferta: Oferta, cliente: Cliente) -> str:
    negocio = oferta.negocio.nombre
    plantilla = oferta.mensaje or (
        "Hola {nombre}, te saluda {negocio}. Tenemos para ti {titulo}: {descuento}% de descuento hasta el {hasta}. "
        "Tienes {puntos} puntos acumulados. ¡Te esperamos!")
    datos = {"nombre": cliente.primer_nombre, "puntos": cliente.puntos, "negocio": negocio, "titulo": oferta.titulo,
             "descuento": pct_texto(oferta.descuento_pct), "hasta": oferta.hasta.strftime("%d/%m")}
    try:
        texto = plantilla.format(**datos)
    except (KeyError, IndexError, ValueError):
        texto = plantilla
    return texto + "\n\n(Si no quieres recibir más ofertas, respóndenos NO.)"


def pct_texto(pct) -> str:
    """Decimal('10.00') → '10'; Decimal('12.50') → '12,5'."""
    texto = format(Decimal(pct).normalize(), "f")
    return texto.replace(".", ",")


def registrar_envio(oferta: Oferta, cliente: Cliente, usuario) -> str:
    """Anota que se envió la oferta y devuelve el enlace de WhatsApp listo para abrir."""
    if not cliente.acepta_ofertas:
        raise ErrorClientes(f"{cliente.nombre} no autorizó recibir ofertas.")
    if not cliente.telefono:
        raise ErrorClientes(f"{cliente.nombre} no tiene celular registrado.")
    if oferta.negocio.giro == "VAPE" and not cliente.mayor_edad_verificado:
        raise ErrorClientes(f"A {cliente.nombre} no se le ha verificado la mayoría de edad (Ley 2354 de 2024).")
    EnvioOferta.objects.get_or_create(oferta=oferta, cliente=cliente, defaults={"usuario": usuario})
    return url_whatsapp(cliente.telefono, mensaje_oferta(oferta, cliente))


def eliminar_cliente(cliente: Cliente, usuario) -> None:
    """Derecho de supresión del cliente final: se borran sus datos; sus ventas quedan sin nombre."""
    from apps.ventas.models import Venta

    negocio = cliente.negocio
    with transaction.atomic():
        Venta.objects.filter(cliente_ref=cliente).update(cliente="", cliente_ref=None)
        pk = cliente.pk
        cliente.delete()
    auditar(negocio, usuario, "eliminar_cliente", negocio, cliente_id=pk)
