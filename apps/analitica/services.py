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
    temporada: str = ""
    demanda_base: float = 0.0


def analizar_producto(producto: Producto, hoy: date | None = None) -> AnalisisProducto:
    hoy = hoy or timezone.localdate()
    config = getattr(producto.negocio, "config", None)
    dias = PARAMS["DIAS_HISTORIA"]
    serie_completa = serie_ventas_diarias(producto, dias, hoy)
    serie = serie_efectiva(producto, dias, hoy)
    # Sin historia útil (siempre agotado) usamos la serie completa
    if not serie:
        serie = serie_completa
    alfa = float(config.alfa_suavizado) if config else PARAMS["ALFA_SUAVIZADO"]
    d = d_base = alg.suavizado_exponencial(serie, alfa)
    sigma = alg.desviacion(serie)
    stock = float(producto.stock_actual)
    L = tiempo_entrega(producto)
    temporada = ""
    if config and config.usa_temporadas:
        horizonte = int(L + config.horizonte_compra_dias)
        t = temporada_activa(producto, hoy, horizonte)
        if t is not None:
            d, temporada = d * float(t.factor), t.nombre
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
        temporada=temporada,
        demanda_base=d_base,
    )


def temporada_activa(producto: Producto, hoy: date, dias: int):
    """Temporada (con mayor factor) que toca los próximos `dias` días para este producto."""
    from django.db.models import Q

    from .models import Temporada

    candidatas = Temporada.objects.filter(negocio_id=producto.negocio_id).filter(
        Q(categoria__isnull=True) | Q(categoria_id=producto.categoria_id)
    )
    mejor = None
    for t in candidatas:
        if any(t.contiene(hoy + timedelta(days=i)) for i in range(max(dias, 1) + 1)):
            if mejor is None or t.factor > mejor.factor:
                mejor = t
    return mejor


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
    todos = [float(f["total"]) for f in completos]
    if len(todos) >= 24:
        return alg.pronostico_holt_winters(todos[-36:])
    serie = todos[-meses:]
    if len(serie) >= 3:
        return alg.pronostico_holt(serie)
    diaria = serie_efectiva(producto, PARAMS["DIAS_HISTORIA"], hoy) or serie_ventas_diarias(
        producto, PARAMS["DIAS_HISTORIA"], hoy)
    config = getattr(producto.negocio, "config", None)
    d = alg.suavizado_exponencial(diaria, float(config.alfa_suavizado) if config else PARAMS["ALFA_SUAVIZADO"])
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



def registrar_y_evaluar_pronosticos(negocio, hoy: date | None = None) -> dict:
    """Guarda el pronóstico de los próximos 30 días y cierra los períodos vencidos con lo realmente vendido.

    Con esto se mide la precisión (error porcentual) del motor por producto."""
    from .models import RegistroPronostico

    hoy = hoy or timezone.localdate()
    cerrados = creados = 0
    for reg in RegistroPronostico.objects.filter(producto__negocio=negocio, real__isnull=True,
                                                 hasta__lt=hoy).select_related("producto"):
        if reg.producto.es_agrupador:  # familia de variantes: lo real es la suma de sus variantes
            reg.real = DemandaDiaria.objects.filter(producto__padre=reg.producto,
                                                    fecha__range=(reg.desde, reg.hasta)).aggregate(
                t=Sum("cantidad"))["t"] or 0
            reg.dias_agotado = _dias_agotada_familia(reg.producto, reg.desde, reg.hasta)
        else:
            reg.real = DemandaDiaria.objects.filter(producto=reg.producto, fecha__range=(reg.desde, reg.hasta)).aggregate(
                t=Sum("cantidad"))["t"] or 0
            reg.dias_agotado = len(dias_sin_stock(reg.producto, reg.desde, reg.hasta))
        reg.save(update_fields=["real", "dias_agotado"])
        cerrados += 1
    config = getattr(negocio, "config", None)
    por_familia = bool(config and config.usa_variantes)
    for producto in Producto.objects.filter(negocio=negocio, activo=True):
        if producto.es_agrupador and not por_familia:
            continue
        if producto.padre_id and por_familia:
            continue  # en ropa y similares se pronostica la familia, no cada talla
        if RegistroPronostico.objects.filter(producto=producto, hasta__gte=hoy).exists():
            continue
        if producto.es_agrupador:
            if not DemandaDiaria.objects.filter(producto__padre=producto).exists():
                continue
            d, _ = demanda_familia(producto, hoy)
            valor = d * 30
        else:
            if not DemandaDiaria.objects.filter(producto=producto).exists():
                continue
            valor = pronostico_mensual(producto, hoy=hoy).valor
        RegistroPronostico.objects.create(producto=producto, desde=hoy, hasta=hoy + timedelta(days=29),
                                          pronosticado=round(valor, 3))
        creados += 1
    return {"creados": creados, "cerrados": cerrados}


def _dias_agotada_familia(padre: Producto, desde: date, hasta: date) -> int:
    """Días en que TODAS las variantes estaban agotadas (la familia no se podía vender)."""
    variantes = list(padre.variantes.all())
    if not variantes:
        return 0
    comunes = None
    for v in variantes:
        dias = dias_sin_stock(v, desde, hasta)
        comunes = dias if comunes is None else comunes & dias
        if not comunes:
            return 0
    return len(comunes)


def precision_pronosticos(negocio) -> list[dict]:
    """Error porcentual medio (MAPE) por producto sobre los períodos ya cerrados."""
    from .models import RegistroPronostico

    por_producto: dict[int, list] = {}
    for reg in RegistroPronostico.objects.filter(producto__negocio=negocio, real__isnull=False).select_related("producto"):
        if reg.error_pct is not None:
            por_producto.setdefault(reg.producto_id, [reg.producto, []])[1].append(reg.error_pct)
    filas = [{"producto": p, "periodos": len(e), "mape": sum(e) / len(e)} for p, e in por_producto.values()]
    return sorted(filas, key=lambda f: f["mape"])


# ---------------------------------------------------------------- ciclo real de compra (Fase 8b · P11)
MIN_ORDENES_CICLO = 3


def ciclo_compra(proveedor=None, hoy: date | None = None, dias: int = 120, negocio=None) -> float | None:
    """Cada cuántos días se compra (mediana entre días de compra de los últimos `dias`): a un proveedor o, con
    `negocio`, a cualquiera (la rutina de compras del negocio).

    None si hay menos de MIN_ORDENES_CICLO compras en días distintos (no hay cómo saberlo todavía)."""
    from statistics import median

    from django.db.models.functions import Coalesce

    from apps.compras.models import OrdenCompra

    hoy = hoy or timezone.localdate()
    tz = timezone.get_current_timezone()
    fechas = sorted({
        f.astimezone(tz).date() for f in OrdenCompra.objects.filter(
            **({"negocio": negocio} if negocio is not None else {"proveedor": proveedor}))
        .exclude(estado__in=[OrdenCompra.Estado.CANCELADA, OrdenCompra.Estado.BORRADOR])
        .annotate(f=Coalesce("fecha_envio", "creado")).values_list("f", flat=True)
        if f and hoy - timedelta(days=dias) <= f.astimezone(tz).date() <= hoy
    })
    if len(fechas) < MIN_ORDENES_CICLO:
        return None
    brechas = [(b - a).days for a, b in zip(fechas, fechas[1:], strict=False)]
    return float(min(60, max(1, median(brechas))))


def horizonte_compra(producto: Producto, hoy: date | None = None, ciclos: dict | None = None) -> tuple[float, str]:
    """Días que debe cubrir un pedido y de dónde sale ese número (para explicarlo).

    Es el mayor entre el horizonte configurado y la rutina real de compras del negocio (cada cuánto hace pedidos).
    Se mide la rutina del NEGOCIO y no la de cada proveedor: la frecuencia con que se le pide a un proveedor depende
    de lo que el propio sistema recomendó (pedidos grandes → menos pedidos → «ciclo» más largo → pedidos más
    grandes…); en el piloto simulado esa retroalimentación aumentó los agotados."""
    config = getattr(producto.negocio, "config", None)
    base = float(config.horizonte_compra_dias if config else 7)
    if not (config and config.horizonte_automatico):
        return base, "configuracion"
    if ciclos is not None and "negocio" in ciclos:
        ciclo = ciclos["negocio"]
    else:
        ciclo = ciclo_compra(negocio=producto.negocio, hoy=hoy)
        if ciclos is not None:
            ciclos["negocio"] = ciclo
    # Solo se alarga: si compras cada 14 días el pedido debe cubrir 14; si compras más seguido que el horizonte
    # configurado, se conserva el horizonte (en el piloto simulado, acortarlo aumentó los agotados).
    return (ciclo, "ciclo") if ciclo and ciclo > base else (base, "configuracion")


# ---------------------------------------------------------------- familias de variantes (Fase 8b · P8)
def serie_familia(padre: Producto, dias: int, hasta: date | None = None) -> list[float]:
    """Ventas diarias de toda la familia (suma de sus variantes): mucho más estable que talla por talla."""
    hasta = hasta or timezone.localdate()
    desde = hasta - timedelta(days=dias - 1)
    totales: dict[date, float] = {}
    for fecha, cant in DemandaDiaria.objects.filter(producto__padre=padre, fecha__range=(desde, hasta)).values_list(
            "fecha", "cantidad"):
        totales[fecha] = totales.get(fecha, 0.0) + float(cant)
    return [totales.get(desde + timedelta(days=i), 0.0) for i in range(dias)]


def curva_variantes(padre: Producto, dias: int = 90, hoy: date | None = None) -> dict[int, float]:
    """Participación de cada variante en las ventas de la familia (la «curva de tallas»).

    Se suaviza con UNA venta ficticia repartida entre todas (1/n a cada una): una talla sin ventas recientes no queda
    en cero para siempre, pero la curva sigue a los datos aunque haya pocas ventas."""
    hoy = hoy or timezone.localdate()
    variantes = list(padre.variantes.filter(activo=True).values_list("pk", flat=True))
    if not variantes:
        return {}
    ventas = dict(DemandaDiaria.objects.filter(producto_id__in=variantes, fecha__gt=hoy - timedelta(days=dias))
                  .values("producto_id").annotate(t=Sum("cantidad")).values_list("producto_id", "t"))
    previo = 1.0 / len(variantes)
    pesos = {pk: float(ventas.get(pk) or 0) + previo for pk in variantes}
    total = sum(pesos.values())
    return {pk: w / total for pk, w in pesos.items()}


def demanda_familia(padre: Producto, hoy: date | None = None) -> tuple[float, float]:
    """(demanda diaria suavizada, desviación) de la familia completa."""
    hoy = hoy or timezone.localdate()
    config = getattr(padre.negocio, "config", None)
    serie = serie_familia(padre, PARAMS["DIAS_HISTORIA"], hoy)
    # Se descartan los días previos a la primera venta de la familia (productos nuevos)
    while serie and serie[0] == 0:
        serie = serie[1:]
    alfa = float(config.alfa_suavizado) if config else PARAMS["ALFA_SUAVIZADO"]
    return alg.suavizado_exponencial(serie, alfa), alg.desviacion(serie)


# ---------------------------------------------------------------- precisión en lenguaje simple (Fase 8b · P12)
def precision_negocio(negocio) -> dict:
    """WAPE del negocio (error ponderado por volumen) y «acierto» = 100 − WAPE.

    A diferencia del MAPE, no se dispara con productos que venden 1 o 2 unidades al mes. Los períodos con muchos
    días agotado se corrigen (lo vendido subestima la demanda) y, si estuvo agotado más de la mitad, se excluyen."""
    from .models import RegistroPronostico

    error = real_total = 0.0
    usados = excluidos = 0
    for reg in RegistroPronostico.objects.filter(producto__negocio=negocio, real__isnull=False):
        real = reg.real_ajustado
        if real is None:
            excluidos += 1
            continue
        error += abs(float(reg.pronosticado) - real)
        real_total += real
        usados += 1
    if not real_total:
        return {"wape": None, "acierto": None, "periodos": usados, "excluidos": excluidos}
    wape = error / real_total * 100
    return {"wape": round(wape, 1), "acierto": round(max(0.0, 100 - wape)), "periodos": usados,
            "excluidos": excluidos}
