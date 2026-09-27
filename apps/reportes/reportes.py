"""Catálogo de reportes.

Cada reporte es una función (negocio, filtros) -> Tabla. Para agregar uno nuevo basta con
escribir la función y registrarla en REPORTES con su título, descripción y permiso.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count, F, Max, Sum
from django.utils import timezone

from apps.catalogo.models import Producto
from apps.core.negocio import del_negocio
from apps.inventario.models import Lote, Movimiento, TipoMovimiento


@dataclass
class Tabla:
    encabezados: list[str]
    filas: list[list]
    # Tipo por columna para formatear: "texto", "numero", "moneda", "fecha", "porcentaje"
    tipos: list[str] = field(default_factory=list)
    totales: list | None = None

    def __post_init__(self):
        if not self.tipos:
            self.tipos = ["texto"] * len(self.encabezados)


@dataclass
class Filtros:
    desde: date | None = None
    hasta: date | None = None
    categoria: int | None = None

    def rango(self, dias_defecto=30):
        hoy = timezone.localdate()
        return self.desde or hoy - timedelta(days=dias_defecto - 1), self.hasta or hoy


def _productos(negocio, f: Filtros):
    qs = del_negocio(negocio, Producto).filter(activo=True, es_agrupador=False).select_related("categoria")
    if f.categoria:
        qs = qs.filter(categoria_id=f.categoria)
    return qs


def _detalles_venta(negocio, f: Filtros):
    from apps.ventas.models import DetalleVenta, Venta

    desde, hasta = f.rango()
    qs = DetalleVenta.objects.filter(venta__negocio=negocio, venta__estado=Venta.Estado.COMPLETADA,
                                     venta__fecha__date__range=(desde, hasta))
    if f.categoria:
        qs = qs.filter(producto__categoria_id=f.categoria)
    return qs


def _suma_columna(filas, i):
    return sum((Decimal(str(fila[i] or 0)) for fila in filas), Decimal("0"))


# ------------------------------------------------------------------ Inventario

def inventario_actual(negocio, f):
    enc = ["SKU", "Producto", "Categoría", "Stock", "Mínimo", "Estado", "Costo", "Precio venta", "Valor"]
    filas = [[p.sku, p.nombre, str(p.categoria or ""), p.stock_actual, p.stock_minimo, p.get_estado_display(),
              p.precio_compra, p.precio_venta, p.valor_inventario] for p in _productos(negocio, f).order_by("nombre")]
    t = Tabla(enc, filas, ["texto", "texto", "texto", "numero", "numero", "texto", "moneda", "moneda", "moneda"])
    t.totales = ["", "Total", "", "", "", "", "", "", _suma_columna(filas, 8)]
    return t


def stock_bajo(negocio, f):
    qs = _productos(negocio, f).filter(stock_actual__gt=0, stock_actual__lte=F("stock_minimo")).order_by("stock_actual")
    return Tabla(["SKU", "Producto", "Stock", "Mínimo", "Faltan para el mínimo"],
                 [[p.sku, p.nombre, p.stock_actual, p.stock_minimo, p.stock_minimo - p.stock_actual] for p in qs],
                 ["texto", "texto", "numero", "numero", "numero"])


def agotados(negocio, f):
    qs = _productos(negocio, f).filter(stock_actual__lte=0).annotate(ultima=Max("movimientos__fecha")).order_by("nombre")
    return Tabla(["SKU", "Producto", "Categoría", "Último movimiento"],
                 [[p.sku, p.nombre, str(p.categoria or ""), p.ultima] for p in qs], ["texto", "texto", "texto", "fecha"])


def por_vencer(negocio, f):
    hoy = timezone.localdate()
    config = negocio.config
    limite = f.hasta or hoy + timedelta(days=config.dias_vencimiento_amarillo)
    qs = del_negocio(negocio, Lote).filter(cantidad__gt=0, fecha_vencimiento__lte=limite).select_related("producto")
    if f.categoria:
        qs = qs.filter(producto__categoria_id=f.categoria)
    filas = [[l.producto.nombre, l.codigo or l.pk, l.fecha_vencimiento, (l.fecha_vencimiento - hoy).days, l.cantidad,
              l.cantidad * l.producto.precio_compra] for l in qs.order_by("fecha_vencimiento")]
    t = Tabla(["Producto", "Lote", "Vence", "Días", "Cantidad", "Valor en riesgo"], filas,
              ["texto", "texto", "fecha", "numero", "numero", "moneda"])
    t.totales = ["Total", "", "", "", "", _suma_columna(filas, 5)]
    return t


def valor_por_categoria(negocio, f):
    filas = (
        _productos(negocio, f).values("categoria__nombre")
        .annotate(productos=Count("id"), unidades=Sum("stock_actual"), valor=Sum(F("stock_actual") * F("precio_compra")),
                  valor_venta=Sum(F("stock_actual") * F("precio_venta")))
        .order_by("-valor")
    )
    datos = [[r["categoria__nombre"] or "Sin categoría", r["productos"], r["unidades"], r["valor"], r["valor_venta"]]
             for r in filas]
    t = Tabla(["Categoría", "Productos", "Unidades", "Valor al costo", "Valor a precio de venta"], datos,
              ["texto", "numero", "numero", "moneda", "moneda"])
    t.totales = ["Total", sum(r[1] for r in datos), _suma_columna(datos, 2), _suma_columna(datos, 3),
                 _suma_columna(datos, 4)]
    return t


def movimientos(negocio, f):
    desde, hasta = f.rango()
    qs = del_negocio(negocio, Movimiento).filter(fecha__date__range=(desde, hasta)).select_related("producto", "usuario")
    if f.categoria:
        qs = qs.filter(producto__categoria_id=f.categoria)
    return Tabla(["Fecha", "Producto", "Tipo", "Cantidad", "Saldo", "Usuario", "Motivo"],
                 [[m.fecha, m.producto.nombre, m.get_tipo_display(), m.cantidad if m.es_entrada else -m.cantidad,
                   m.stock_resultante, str(m.usuario or ""), m.motivo] for m in qs.order_by("-fecha")[:5000]],
                 ["fecha", "texto", "texto", "numero", "numero", "texto", "texto"])


def historial_ajustes(negocio, f):
    desde, hasta = f.rango(90)
    qs = del_negocio(negocio, Movimiento).filter(
        tipo__in=[TipoMovimiento.ENTRADA_AJUSTE, TipoMovimiento.SALIDA_AJUSTE, TipoMovimiento.SALIDA_DANADO],
        fecha__date__range=(desde, hasta),
    ).select_related("producto", "usuario")
    filas = [[m.fecha, m.producto.nombre, m.get_tipo_display(), m.cantidad if m.es_entrada else -m.cantidad,
              (m.cantidad if m.es_entrada else -m.cantidad) * m.costo_unitario, str(m.usuario or ""), m.motivo,
              "⚠️" if m.marcado_anomalo else ""] for m in qs.order_by("-fecha")]
    t = Tabla(["Fecha", "Producto", "Tipo", "Cantidad", "Valor", "Usuario", "Motivo", "Inusual"], filas,
              ["fecha", "texto", "texto", "numero", "moneda", "texto", "texto", "texto"])
    t.totales = ["Total", "", "", "", _suma_columna(filas, 4), "", "", ""]
    return t


# ------------------------------------------------------------------ Ventas y compras

def ventas(negocio, f):
    from apps.ventas.models import Venta

    desde, hasta = f.rango()
    qs = del_negocio(negocio, Venta).filter(fecha__date__range=(desde, hasta)).select_related("vendedor")
    filas = [[v.pk, v.fecha, str(v.vendedor), v.get_medio_pago_display(), v.cliente, v.get_estado_display(),
              v.total if v.estado == Venta.Estado.COMPLETADA else 0] for v in qs.order_by("-fecha")]
    t = Tabla(["#", "Fecha", "Vendedor", "Medio de pago", "Cliente", "Estado", "Total"], filas,
              ["numero", "fecha", "texto", "texto", "texto", "texto", "moneda"])
    t.totales = ["", "Total", "", "", "", "", _suma_columna(filas, 6)]
    return t


def _ranking(negocio, f, orden):
    filas = (
        _detalles_venta(negocio, f).values("producto__sku", "producto__nombre")
        .annotate(unidades=Sum("cantidad"), ingreso=Sum(F("cantidad") * F("precio_unitario") - F("descuento")),
                  ventas=Count("venta", distinct=True))
        .order_by(orden)[:50]
    )
    return Tabla(["SKU", "Producto", "Unidades", "Ventas", "Ingreso"],
                 [[r["producto__sku"], r["producto__nombre"], r["unidades"], r["ventas"], r["ingreso"]] for r in filas],
                 ["texto", "texto", "numero", "numero", "moneda"])


def mas_vendidos(negocio, f):
    return _ranking(negocio, f, "-unidades")


def menos_vendidos(negocio, f):
    """Incluye productos con stock que no se vendieron en el período."""
    desde, hasta = f.rango()
    vendidos = dict(_detalles_venta(negocio, f).values_list("producto_id").annotate(u=Sum("cantidad")))
    filas = [[p.sku, p.nombre, vendidos.get(p.pk, 0), p.stock_actual, p.valor_inventario]
             for p in _productos(negocio, f).filter(stock_actual__gt=0)]
    filas.sort(key=lambda r: (r[2], -r[4]))
    return Tabla(["SKU", "Producto", "Unidades vendidas", "Stock", "Valor en stock"], filas[:50],
                 ["texto", "texto", "numero", "numero", "moneda"])


def utilidad(negocio, f):
    filas = (
        _detalles_venta(negocio, f).values("producto__sku", "producto__nombre")
        .annotate(unidades=Sum("cantidad"), ingreso=Sum(F("cantidad") * F("precio_unitario") - F("descuento")),
                  costo=Sum(F("cantidad") * F("costo_unitario")))
        .order_by("-ingreso")
    )
    datos = []
    for r in filas:
        ganancia = (r["ingreso"] or 0) - (r["costo"] or 0)
        margen = (ganancia / r["ingreso"] * 100) if r["ingreso"] else 0
        datos.append([r["producto__sku"], r["producto__nombre"], r["unidades"], r["ingreso"], r["costo"], ganancia, margen])
    t = Tabla(["SKU", "Producto", "Unidades", "Ingreso", "Costo", "Utilidad", "Margen"], datos,
              ["texto", "texto", "numero", "moneda", "moneda", "moneda", "porcentaje"])
    ingreso, util = _suma_columna(datos, 3), _suma_columna(datos, 5)
    t.totales = ["", "Total", "", ingreso, _suma_columna(datos, 4), util, (util / ingreso * 100) if ingreso else 0]
    return t


def compras(negocio, f):
    from apps.compras.models import DetalleOrdenCompra, OrdenCompra

    desde, hasta = f.rango(90)
    qs = DetalleOrdenCompra.objects.filter(
        orden__negocio=negocio, orden__creado__date__range=(desde, hasta)
    ).exclude(orden__estado=OrdenCompra.Estado.CANCELADA).select_related("orden__proveedor", "producto")
    if f.categoria:
        qs = qs.filter(producto__categoria_id=f.categoria)
    filas = [[d.orden_id, d.orden.creado, d.orden.proveedor.nombre, d.producto.nombre, d.cantidad_pedida,
              d.cantidad_recibida, d.costo_unitario, d.subtotal, d.orden.get_estado_display()]
             for d in qs.order_by("-orden__creado")]
    t = Tabla(["Orden", "Fecha", "Proveedor", "Producto", "Pedido", "Recibido", "Costo", "Subtotal", "Estado"], filas,
              ["numero", "fecha", "texto", "texto", "numero", "numero", "moneda", "moneda", "texto"])
    t.totales = ["", "Total", "", "", "", "", "", _suma_columna(filas, 7), ""]
    return t


# ------------------------------------------------------------------ Inteligencia

def rotacion_abc(negocio, f):
    """Versión masiva: 3 consultas para todo el catálogo (antes, ~9 por producto)."""
    from django.conf import settings

    from apps.analitica import algoritmos as alg
    from apps.analitica.models import DemandaDiaria
    from apps.analitica.services import clasificacion_abc

    params = settings.INVENTARIO_INTELIGENTE
    config = negocio.config
    hoy = timezone.localdate()
    dias = params["DIAS_HISTORIA"]
    desde = hoy - timedelta(days=dias - 1)
    abc = clasificacion_abc(negocio)
    productos = list(_productos(negocio, f))
    series: dict[int, dict] = {}
    for pid, fecha, cant in DemandaDiaria.objects.filter(
        producto__in=productos, fecha__range=(desde, hoy)
    ).values_list("producto_id", "fecha", "cantidad"):
        series.setdefault(pid, {})[fecha] = float(cant)
    ultimas = dict(
        DemandaDiaria.objects.filter(producto__in=productos, cantidad__gt=0)
        .values("producto_id").annotate(u=Max("fecha")).values_list("producto_id", "u")
    )
    alfa = float(config.alfa_suavizado)
    filas = []
    for p in productos:
        datos = series.get(p.pk, {})
        serie = [datos.get(desde + timedelta(days=i), 0.0) for i in range(dias)]
        d = alg.suavizado_exponencial(serie, alfa)
        ultima = ultimas.get(p.pk)
        rot = alg.clasificar_rotacion(sum(1 for x in serie if x > 0), dias, (hoy - ultima).days if ultima else None,
                                      config.dias_sin_movimiento)
        cobertura = alg.dias_de_cobertura(float(p.stock_actual), d)
        filas.append([p.sku, p.nombre, abc.get(p.pk, "C"), rot.capitalize(), round(d, 2),
                      round(cobertura) if cobertura is not None else "", p.stock_actual])
    filas.sort(key=lambda r: (r[2], -r[4]))
    return Tabla(["SKU", "Producto", "Clase ABC", "Rotación", "Venta diaria", "Días de cobertura", "Stock"], filas,
                 ["texto", "texto", "texto", "texto", "numero", "numero", "numero"])


def precision(negocio, f):
    from apps.analitica.services import precision_pronosticos

    filas = [[r["producto"].sku, r["producto"].nombre, r["periodos"], r["mape"],
              "Buena" if r["mape"] <= 20 else ("Aceptable" if r["mape"] <= 40 else "Baja")]
             for r in precision_pronosticos(negocio)]
    return Tabla(["SKU", "Producto", "Períodos evaluados", "Error promedio", "Precisión"], filas,
                 ["texto", "texto", "numero", "porcentaje", "texto"])


REPORTES = {
    # clave: (título, descripción, función, permiso, grupo)
    "inventario-actual": ("Inventario actual", "Stock, estado y valor de cada producto.", inventario_actual,
                          "ver_reportes", "Inventario"),
    "stock-bajo": ("Stock bajo", "Productos por debajo del mínimo.", stock_bajo, "ver_reportes", "Inventario"),
    "agotados": ("Agotados", "Productos sin existencias.", agotados, "ver_reportes", "Inventario"),
    "por-vencer": ("Próximos a vencer", "Lotes que vencen pronto y su valor en riesgo.", por_vencer, "ver_reportes",
                   "Inventario"),
    "valor-inventario": ("Valor del inventario", "Valor al costo y a precio de venta por categoría.",
                         valor_por_categoria, "ver_reportes_financieros", "Inventario"),
    "movimientos": ("Movimientos", "Todas las entradas y salidas del período.", movimientos, "ver_reportes",
                    "Inventario"),
    "historial-ajustes": ("Historial de ajustes", "Ajustes y daños con responsable y motivo.", historial_ajustes,
                          "ver_reportes", "Inventario"),
    "ventas": ("Ventas", "Ventas del período con medio de pago y vendedor.", ventas, "ver_reportes_financieros",
               "Ventas y compras"),
    "mas-vendidos": ("Más vendidos", "Top 50 por unidades.", mas_vendidos, "ver_reportes", "Ventas y compras"),
    "menos-vendidos": ("Menos vendidos", "Productos con stock que casi no se venden.", menos_vendidos, "ver_reportes",
                       "Ventas y compras"),
    "utilidad": ("Utilidad estimada", "Ingreso, costo, utilidad y margen por producto.", utilidad,
                 "ver_reportes_financieros", "Ventas y compras"),
    "compras": ("Compras", "Órdenes y facturas por proveedor.", compras, "ver_reportes_financieros", "Ventas y compras"),
    "rotacion-abc": ("Rotación y ABC", "Qué productos mueven tu negocio y cuáles están quietos.", rotacion_abc,
                     "ver_reportes", "Inteligencia"),
    "precision-pronosticos": ("Precisión de pronósticos", "Qué tan acertado ha sido el sistema.", precision,
                              "ver_reportes", "Inteligencia"),
}

