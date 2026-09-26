"""Pedido sugerido explicado. El sistema sugiere; el empresario decide."""

from collections import defaultdict

from django.db import transaction

from apps.analitica import algoritmos as alg
from apps.analitica.services import analizar_producto
from apps.catalogo.models import Producto
from apps.compras.models import DetalleOrdenCompra, OrdenCompra

from .models import RecomendacionCompra


def _n(x):
    return f"{x:,.0f}".replace(",", ".") if abs(x - round(x)) < 1e-9 else f"{x:,.1f}"


def recomendar_producto(producto: Producto) -> RecomendacionCompra | None:
    a = analizar_producto(producto)
    config = getattr(producto.negocio, "config", None)
    horizonte = config.horizonte_compra_dias if config else 7
    necesita = a.stock + a.en_transito <= a.punto_reorden or a.stock <= float(producto.stock_minimo)
    if not necesita:
        return None

    multiplo = 1
    if producto.proveedor_principal_id:
        pp = producto.proveedores.filter(proveedor_id=producto.proveedor_principal_id).first()
        multiplo = pp.multiplo_empaque if pp else 1

    cantidad = alg.pedido_sugerido(
        stock=a.stock,
        demanda_diaria=a.demanda_diaria,
        tiempo_entrega=a.tiempo_entrega,
        horizonte=horizonte,
        ss=a.stock_seguridad,
        en_transito=a.en_transito,
        multiplo=multiplo,
    )
    if cantidad <= 0:
        return None

    explicacion = (
        f"Tienes {_n(a.stock)} unidades de {producto.nombre}. Vendes aproximadamente {_n(a.demanda_diaria)} por día "
        f"(~{_n(a.demanda_diaria * 7)} por semana) y tu proveedor tarda {_n(a.tiempo_entrega)} días. "
        f"Para cubrir {horizonte} días más un stock de seguridad de {_n(a.stock_seguridad)}, "
        f"se recomienda pedir aproximadamente {cantidad} unidades."
    )
    if a.en_transito:
        explicacion += f" Ya hay {_n(a.en_transito)} unidades en camino."

    rec, _ = RecomendacionCompra.objects.update_or_create(
        producto=producto,
        estado=RecomendacionCompra.Estado.PENDIENTE,
        defaults=dict(
            negocio=producto.negocio,
            proveedor=producto.proveedor_principal,
            cantidad_sugerida=cantidad,
            demanda_diaria=round(a.demanda_diaria, 3),
            stock_seguridad=round(a.stock_seguridad, 3),
            tiempo_entrega=a.tiempo_entrega,
            stock_al_calcular=a.stock,
            explicacion=explicacion,
        ),
    )
    return rec


def generar_recomendaciones(negocio) -> list[RecomendacionCompra]:
    recs = []
    for p in Producto.objects.filter(negocio=negocio, activo=True).select_related(
        "negocio__config", "proveedor_principal"
    ):
        rec = recomendar_producto(p)
        if rec:
            recs.append(rec)
    return recs


@transaction.atomic
def crear_ordenes_desde_recomendaciones(recomendaciones, usuario) -> list[OrdenCompra]:
    """Agrupa recomendaciones aceptadas por proveedor y crea una orden en BORRADOR por cada uno."""
    por_proveedor = defaultdict(list)
    for rec in recomendaciones:
        if rec.proveedor_id is None:
            continue
        por_proveedor[rec.proveedor].append(rec)
    ordenes = []
    for proveedor, recs in por_proveedor.items():
        orden = OrdenCompra.objects.create(negocio=proveedor.negocio, proveedor=proveedor, creada_por=usuario)
        for rec in recs:
            DetalleOrdenCompra.objects.create(
                orden=orden,
                producto=rec.producto,
                cantidad_pedida=rec.cantidad_sugerida,
                costo_unitario=rec.producto.precio_compra,
                recomendacion=rec,
            )
            rec.estado = RecomendacionCompra.Estado.ACEPTADA
            rec.save(update_fields=["estado"])
        ordenes.append(orden)
    return ordenes
