"""Servicios de analítica que conectan los algoritmos con los datos."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.db.models import F, Sum
from django.utils import timezone

from apps.catalogo.models import EstadoStock, Producto

from . import algoritmos as alg
from .models import DemandaDiaria

PARAMS = settings.INVENTARIO_INTELIGENTE


def acumular_demanda_diaria(producto: Producto, fecha: date, cantidad) -> None:
    obj, _ = DemandaDiaria.objects.get_or_create(producto=producto, fecha=fecha)
    DemandaDiaria.objects.filter(pk=obj.pk).update(cantidad=F("cantidad") + Decimal(str(cantidad)))


def serie_ventas_diarias(producto: Producto, dias: int, hasta: date | None = None) -> list[float]:
    """Serie completa (con ceros en días sin venta) de los últimos `dias` días."""
    hasta = hasta or timezone.localdate()
    desde = hasta - timedelta(days=dias - 1)
    datos = dict(
        DemandaDiaria.objects.filter(producto=producto, fecha__range=(desde, hasta)).values_list("fecha", "cantidad")
    )
    return [float(datos.get(desde + timedelta(days=i), 0)) for i in range(dias)]


def dias_sin_stock(producto: Producto, desde: date, hasta: date) -> set[date]:
    """Días en que el producto terminó sin stock (no se vendió porque no había, no porque no se pidiera)."""
    from apps.inventario.models import Movimiento

    tz = timezone.get_current_timezone()
    previo = (
        Movimiento.objects.filter(producto=producto, fecha__date__lt=desde).order_by("-fecha", "-id")
        .values_list("stock_resultante", flat=True).first()
    )
    stock = float(previo) if previo is not None else 0.0
    cierres: dict[date, float] = {}
    for fecha, saldo in (
        Movimiento.objects.filter(producto=producto, fecha__date__range=(desde, hasta))
        .order_by("fecha", "id").values_list("fecha", "stock_resultante")
    ):
        cierres[fecha.astimezone(tz).date()] = float(saldo)
    agotados, dia = set(), desde
    while dia <= hasta:
        stock = cierres.get(dia, stock)
        if stock <= 0:
            agotados.add(dia)
        dia += timedelta(days=1)
    return agotados


def serie_efectiva(producto: Producto, dias: int, hoy: date | None = None) -> list[float]:
    """Ventas diarias excluyendo los días agotados sin ventas (corrige la demanda censurada)."""
    hoy = hoy or timezone.localdate()
    serie = serie_ventas_diarias(producto, dias, hoy)
    desde = hoy - timedelta(days=dias - 1)
    agotados = dias_sin_stock(producto, desde, hoy)
    return [x for i, x in enumerate(serie) if x > 0 or (desde + timedelta(days=i)) not in agotados]


def tiempo_entrega(producto: Producto) -> float:
    if producto.proveedor_principal_id:
        pp = producto.proveedores.filter(proveedor_id=producto.proveedor_principal_id).first()
        if pp and pp.tiempo_entrega_dias is not None:
            return pp.tiempo_entrega_dias
        return float(producto.proveedor_principal.tiempo_entrega_real())
    config = getattr(producto.negocio, "config", None)
    return config.tiempo_entrega_defecto if config else 3


def unidades_en_transito(producto: Producto) -> float:
    from apps.compras.models import DetalleOrdenCompra, OrdenCompra

    pendientes = DetalleOrdenCompra.objects.filter(
        producto=producto,
        orden__estado__in=[
            OrdenCompra.Estado.ENVIADA,
            OrdenCompra.Estado.CONFIRMADA,
            OrdenCompra.Estado.RECIBIDA_PARCIAL,
        ],
    ).aggregate(p=Sum(F("cantidad_pedida") - F("cantidad_recibida")))["p"]
    return float(pendientes or 0)


@dataclass
class AnalisisProducto:
    producto: Producto
    stock: float
    demanda_diaria: float
    sigma: float
    cobertura_dias: float | None
    tiempo_entrega: float
    stock_seguridad: float
    punto_reorden: float
    en_transito: float
    rotacion: str
    estado: str
    dias_desde_ultima_venta: int | None


def analizar_producto(producto: Producto, hoy: date | None = None) -> AnalisisProducto:
    hoy = hoy or timezone.localdate()
    config = getattr(producto.negocio, "config", None)
    dias = PARAMS["DIAS_HISTORIA"]
    serie_completa = serie_ventas_diarias(producto, dias, hoy)
    serie = serie_efectiva(producto, dias, hoy)
    # Sin historia útil (siempre agotado) usamos la serie completa
    if not serie:
        serie = serie_completa
    d = alg.suavizado_exponencial(serie, PARAMS["ALFA_SUAVIZADO"])
    sigma = alg.desviacion(serie)
    stock = float(producto.stock_actual)
    L = tiempo_entrega(producto)
    ss = alg.stock_seguridad(sigma, L, float(producto.stock_minimo), PARAMS["Z_NIVEL_SERVICIO"])
    cobertura = alg.dias_de_cobertura(stock, d)

    ultima = DemandaDiaria.objects.filter(producto=producto, cantidad__gt=0).order_by("-fecha").first()
    dias_ultima = (hoy - ultima.fecha).days if ultima else None
    rotacion = alg.clasificar_rotacion(
        sum(1 for x in serie if x > 0), max(len(serie), 1), dias_ultima, config.dias_sin_movimiento if config else 45
    )

    estado = producto.estado_basico()
    if estado != EstadoStock.AGOTADO and cobertura is not None and cobertura < L:
        estado = EstadoStock.CRITICO
    elif estado == EstadoStock.NORMAL and cobertura is not None and cobertura > (config.dias_exceso if config else 90):
        estado = EstadoStock.EXCESO

    return AnalisisProducto(
        producto=producto,
        stock=stock,
        demanda_diaria=d,
        sigma=sigma,
        cobertura_dias=cobertura,
        tiempo_entrega=L,
        stock_seguridad=ss,
        punto_reorden=alg.punto_de_reorden(d, L, ss),
        en_transito=unidades_en_transito(producto),
        rotacion=rotacion,
        estado=estado,
        dias_desde_ultima_venta=dias_ultima,
    )


def pronostico_mensual(producto: Producto, meses: int = 6, hoy: date | None = None) -> alg.Pronostico:
    """Pronóstico de unidades para los próximos 30 días.

    - Con ≥ 3 meses COMPLETOS de historia: método de Holt sobre ventas mensuales (el mes en curso,
      incompleto, se excluye porque haría parecer que las ventas cayeron).
    - Con menos historia: ritmo diario actual × 30, con un rango basado en la variabilidad diaria.
    """
    from django.db.models.functions import TruncMonth

    hoy = hoy or timezone.localdate()
    inicio_mes = hoy.replace(day=1)
    primera = DemandaDiaria.objects.filter(producto=producto).order_by("fecha").values_list("fecha", flat=True).first()
    filas = (
        DemandaDiaria.objects.filter(producto=producto, fecha__lt=inicio_mes)
        .annotate(mes=TruncMonth("fecha")).values("mes").annotate(total=Sum("cantidad")).order_by("mes")
    )
    completos = [f for f in filas if primera and f["mes"] >= primera.replace(day=1) and
                 (f["mes"] > primera.replace(day=1) or primera.day == 1)]
    serie = [float(f["total"]) for f in completos][-meses:]
    if len(serie) >= 3:
        return alg.pronostico_holt(serie)
    diaria = serie_ventas_diarias(producto, PARAMS["DIAS_HISTORIA"], hoy)
    d = alg.suavizado_exponencial(diaria, PARAMS["ALFA_SUAVIZADO"])
    sigma = alg.desviacion(diaria)
    valor = d * 30
    margen = 1.28 * sigma * (30 ** 0.5)  # ~80 % de confianza
    return alg.Pronostico(valor, max(0.0, valor - margen), valor + margen)


MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def ventas_mensuales(producto: Producto, meses: int = 6, hoy: date | None = None) -> list[dict]:
    """Unidades vendidas por mes (incluye meses sin ventas) para gráficos."""
    hoy = hoy or timezone.localdate()
    inicio = hoy.replace(day=1)
    for _ in range(meses - 1):
        inicio = (inicio - timedelta(days=1)).replace(day=1)
    totales = {}
    for fecha, cant in DemandaDiaria.objects.filter(producto=producto, fecha__gte=inicio).values_list("fecha", "cantidad"):
        clave = (fecha.year, fecha.month)
        totales[clave] = totales.get(clave, 0) + float(cant)
    datos, cursor = [], inicio
    for _ in range(meses):
        datos.append({"etiqueta": f"{MESES[cursor.month - 1]}", "valor": totales.get((cursor.year, cursor.month), 0)})
        cursor = (cursor + timedelta(days=32)).replace(day=1)
    return datos



def clasificacion_abc(negocio, dias: int = 90, hoy: date | None = None) -> dict[int, str]:
    """Análisis ABC por ingresos: A = 80 % de las ventas, B = siguiente 15 %, C = resto."""
    from apps.ventas.models import DetalleVenta, Venta

    hoy = hoy or timezone.localdate()
    filas = (
        DetalleVenta.objects.filter(venta__negocio=negocio, venta__estado=Venta.Estado.COMPLETADA,
                                    venta__fecha__date__gte=hoy - timedelta(days=dias))
        .values("producto_id").annotate(ingreso=Sum(F("cantidad") * F("precio_unitario") - F("descuento")))
        .order_by("-ingreso")
    )
    total = sum(float(f["ingreso"] or 0) for f in filas)
    resultado, acumulado = {}, 0.0
    for f in filas:
        acumulado += float(f["ingreso"] or 0)
        proporcion = acumulado / total if total else 1
        resultado[f["producto_id"]] = "A" if proporcion <= 0.80 or not resultado else ("B" if proporcion <= 0.95 else "C")
    return resultado
