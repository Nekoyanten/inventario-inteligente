"""Indicadores de desempeño del proveedor."""

from django.db.models import Avg, Count, Q

from apps.compras.models import OrdenCompra


def desempeno(proveedor) -> dict:
    ordenes = OrdenCompra.objects.filter(proveedor=proveedor, es_compra_directa=False)
    recibidas = ordenes.filter(estado=OrdenCompra.Estado.RECIBIDA)
    con_tiempo = recibidas.exclude(dias_entrega__isnull=True)
    stats = con_tiempo.aggregate(
        promedio=Avg("dias_entrega"),
        a_tiempo=Count("id", filter=Q(dias_entrega__lte=proveedor.tiempo_entrega_dias)),
        total=Count("id"),
    )
    parciales = ordenes.filter(estado=OrdenCompra.Estado.RECIBIDA_PARCIAL).count()
    total = stats["total"] or 0
    return {
        "ordenes": ordenes.count(),
        "recibidas": recibidas.count(),
        "tiempo_promedio": round(stats["promedio"], 1) if stats["promedio"] is not None else None,
        "tiempo_prometido": proveedor.tiempo_entrega_dias,
        "cumplimiento_pct": round(stats["a_tiempo"] / total * 100) if total else None,
        "parciales": parciales,
        "compras_directas": OrdenCompra.objects.filter(proveedor=proveedor, es_compra_directa=True).count(),
    }
