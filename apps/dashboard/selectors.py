"""Responde en una pantalla: ¿Cómo está mi negocio?"""

from datetime import date, timedelta
from decimal import Decimal

from django.db.models import F, Sum
from django.utils import timezone

from apps.alertas.models import Alerta
from apps.catalogo.models import Producto
from apps.inventario.models import Lote
from apps.ventas.models import Venta


def _ventas_mes(negocio, inicio, fin):
    return Venta.objects.filter(
        negocio=negocio, estado=Venta.Estado.COMPLETADA, fecha__gte=inicio, fecha__lt=fin
    ).aggregate(t=Sum("total"))["t"] or Decimal("0")


def resumen_negocio(negocio, hoy: date | None = None) -> dict:
    hoy = hoy or timezone.localdate()
    productos = Producto.objects.filter(negocio=negocio, activo=True)
    config = getattr(negocio, "config", None)

    inicio_mes = hoy.replace(day=1)
    inicio_mes_ant = (inicio_mes - timedelta(days=1)).replace(day=1)
    tz = timezone.get_current_timezone()
    to_dt = lambda d: timezone.make_aware(timezone.datetime(d.year, d.month, d.day), tz)  # noqa: E731
    ventas_mes = _ventas_mes(negocio, to_dt(inicio_mes), to_dt(hoy + timedelta(days=1)))
    ventas_ant = _ventas_mes(negocio, to_dt(inicio_mes_ant), to_dt(inicio_mes))
    variacion = ((ventas_mes - ventas_ant) / ventas_ant * 100) if ventas_ant else None

    por_vencer = 0
    if config and config.usa_vencimientos:
        por_vencer = (
            Lote.objects.filter(
                producto__negocio=negocio,
                cantidad__gt=0,
                fecha_vencimiento__range=(hoy, hoy + timedelta(days=config.dias_vencimiento_amarillo)),
            )
            .values("producto")
            .distinct()
            .count()
        )

    alertas = Alerta.objects.filter(negocio=negocio, estado__in=[Alerta.Estado.ABIERTA, Alerta.Estado.VISTA])
    # Inventario inmovilizado = valor de los productos con alerta abierta de baja rotación
    # (misma regla que ve el usuario en la bandeja de alertas, para que las cifras coincidan).
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
        "ventas": {"mes": ventas_mes, "mes_anterior": ventas_ant, "variacion_pct": variacion},
        "inmovilizado": inmovilizado,
        "alertas": {
            "actuar": alertas.filter(severidad=Alerta.Severidad.ACTUAR).count(),
            "revisar": alertas.filter(severidad=Alerta.Severidad.REVISAR).count(),
            "vencimientos": alertas.filter(tipo__in=[Alerta.Tipo.VENCIMIENTO, Alerta.Tipo.VENCIDO]).count(),
            "ultimas": list(alertas.select_related("producto")[:8]),
        },
    }
