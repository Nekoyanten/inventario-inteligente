"""Responde en una pantalla: ¿Cómo está mi negocio?"""

from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, F, Sum
from django.utils import timezone

from apps.alertas.models import Alerta
from apps.catalogo.models import Producto
from apps.inventario.models import Lote
from apps.ventas.models import DetalleVenta, Venta


def _rango(desde, hasta):
    tz = timezone.get_current_timezone()
    a = timezone.make_aware(timezone.datetime(desde.year, desde.month, desde.day), tz)
    b = timezone.make_aware(timezone.datetime(hasta.year, hasta.month, hasta.day), tz)
    return a, b


def _ventas(negocio, desde, hasta):
    a, b = _rango(desde, hasta)
    return Venta.objects.filter(negocio=negocio, estado=Venta.Estado.COMPLETADA, fecha__gte=a, fecha__lt=b)


def _utilidad(negocio, desde, hasta):
    a, b = _rango(desde, hasta)
    fila = DetalleVenta.objects.filter(
        venta__negocio=negocio, venta__estado=Venta.Estado.COMPLETADA, venta__fecha__gte=a, venta__fecha__lt=b
    ).aggregate(
        ingreso=Sum(F("cantidad") * F("precio_unitario") - F("descuento")),
        costo=Sum(F("cantidad") * F("costo_unitario")),
    )
    return (fila["ingreso"] or Decimal("0")) - (fila["costo"] or Decimal("0"))


def ventas_diarias(negocio, dias=30, hoy=None):
    hoy = hoy or timezone.localdate()
    desde = hoy - timedelta(days=dias - 1)
    tz = timezone.get_current_timezone()
    totales = {}
    for fecha, total in _ventas(negocio, desde, hoy + timedelta(days=1)).values_list("fecha", "total"):
        dia = fecha.astimezone(tz).date()
        totales[dia] = totales.get(dia, 0) + float(total)
    return [{"etiqueta": (desde + timedelta(days=i)).strftime("%d/%m"), "valor": totales.get(desde + timedelta(days=i), 0)}
            for i in range(dias)]


def top_productos(negocio, dias=30, limite=5, hoy=None):
    hoy = hoy or timezone.localdate()
    a, b = _rango(hoy - timedelta(days=dias - 1), hoy + timedelta(days=1))
    return list(
        DetalleVenta.objects.filter(venta__negocio=negocio, venta__estado=Venta.Estado.COMPLETADA,
                                    venta__fecha__gte=a, venta__fecha__lt=b)
        .values("producto_id", "producto__nombre")
        .annotate(unidades=Sum("cantidad"), ingreso=Sum(F("cantidad") * F("precio_unitario") - F("descuento")))
        .order_by("-ingreso")[:limite]
    )


def resumen_negocio(negocio, hoy=None) -> dict:
    hoy = hoy or timezone.localdate()
    productos = Producto.objects.filter(negocio=negocio, activo=True, es_agrupador=False).exclude(tipo="PREPARADO")
    config = getattr(negocio, "config", None)

    inicio_mes = hoy.replace(day=1)
    inicio_mes_ant = (inicio_mes - timedelta(days=1)).replace(day=1)
    # Comparación justa: mismo número de días del mes anterior
    dia_equivalente = min(hoy.day, (inicio_mes - timedelta(days=1)).day)
    fin_ant = inicio_mes_ant + timedelta(days=dia_equivalente)
    manana = hoy + timedelta(days=1)

    ventas_mes = _ventas(negocio, inicio_mes, manana).aggregate(t=Sum("total"), n=Count("id"))
    ventas_ant = _ventas(negocio, inicio_mes_ant, fin_ant).aggregate(t=Sum("total"))["t"] or Decimal("0")
    total_mes = ventas_mes["t"] or Decimal("0")
    variacion = ((total_mes - ventas_ant) / ventas_ant * 100) if ventas_ant else None
    hoy_ventas = _ventas(negocio, hoy, manana).aggregate(t=Sum("total"), n=Count("id"))

    por_vencer = 0
    if config and config.usa_vencimientos:
        por_vencer = Lote.objects.filter(
            producto__negocio=negocio, cantidad__gt=0,
            fecha_vencimiento__range=(hoy, hoy + timedelta(days=config.dias_vencimiento_amarillo)),
        ).values("producto").distinct().count()

    alertas = Alerta.objects.filter(negocio=negocio, estado__in=[Alerta.Estado.ABIERTA, Alerta.Estado.VISTA])
    # Inventario inmovilizado = valor de los productos con alerta abierta de baja rotación
    inmovilizado = sum(
        (Decimal(str(a.datos.get("valor_inmovilizado", 0))) for a in alertas.filter(tipo=Alerta.Tipo.BAJA_ROTACION)),
        Decimal("0"),
    )
    return {
        "inventario": {
            "productos": productos.count(),
            "stock_bajo": productos.filter(stock_actual__gt=0, stock_actual__lte=F("stock_minimo")).count(),
            "agotados": productos.filter(stock_actual__lte=0).count(),
            "por_vencer": por_vencer,
            "valor_total": productos.aggregate(v=Sum(F("stock_actual") * F("precio_compra")))["v"] or Decimal("0"),
        },
        "ventas": {
            "mes": total_mes, "mes_anterior": ventas_ant, "variacion_pct": variacion,
            "numero_mes": ventas_mes["n"], "ticket_promedio": (total_mes / ventas_mes["n"]) if ventas_mes["n"] else 0,
            "hoy": hoy_ventas["t"] or Decimal("0"), "numero_hoy": hoy_ventas["n"],
            "utilidad_mes": _utilidad(negocio, inicio_mes, manana),
        },
        "inmovilizado": inmovilizado,
        "alertas": {
            "actuar": alertas.filter(severidad=Alerta.Severidad.ACTUAR).count(),
            "revisar": alertas.filter(severidad=Alerta.Severidad.REVISAR).count(),
            "vencimientos": alertas.filter(tipo__in=[Alerta.Tipo.VENCIMIENTO, Alerta.Tipo.VENCIDO]).count(),
            "ultimas": list(alertas.select_related("producto").order_by("-severidad", "-creado")[:6]),
        },
        "grafico_ventas": ventas_diarias(negocio, 30, hoy),
        "top": top_productos(negocio, 30, 5, hoy),
    }


def resumen_vendedor(negocio, usuario, hoy=None) -> dict:
    hoy = hoy or timezone.localdate()
    mias = _ventas(negocio, hoy, hoy + timedelta(days=1)).filter(vendedor=usuario).aggregate(t=Sum("total"), n=Count("id"))
    return {"hoy": mias["t"] or Decimal("0"), "numero_hoy": mias["n"]}
