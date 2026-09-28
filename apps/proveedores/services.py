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
        "entregas": total,
        "pocos_datos": 0 < total < MINIMO_ENTREGAS_CONFIABLE,
        "ordenes": ordenes.count(),
        "recibidas": recibidas.count(),
        "tiempo_promedio": round(stats["promedio"], 1) if stats["promedio"] is not None else None,
        "tiempo_prometido": proveedor.tiempo_entrega_dias,
        "cumplimiento_pct": round(stats["a_tiempo"] / total * 100) if total else None,
        "parciales": parciales,
        "compras_directas": OrdenCompra.objects.filter(proveedor=proveedor, es_compra_directa=True).count(),
    }


MINIMO_ENTREGAS_CONFIABLE = 3


class ErrorProveedor(Exception):
    pass


def reemplazar_proveedor(*, origen, destino, usuario, categoria=None, ordenes="esperar", desactivar=True) -> dict:
    """Pasa los productos de `origen` a `destino` en un solo paso (cambio de proveedor).

    - categoria: solo los productos de esa categoría (None = todos).
    - ordenes: qué hacer con las órdenes abiertas de `origen`:
        "esperar"  → se dejan como están (la mercancía ya viene en camino);
        "cancelar" → se cancelan (el inventario en tránsito deja de contarse);
      las órdenes en BORRADOR (aún no enviadas) siempre se pasan a `destino`.
    - desactivar: deja a `origen` inactivo (solo si ya no suministra nada).
    """
    from django.db import transaction

    from apps.catalogo.models import Producto
    from apps.compras.models import OrdenCompra
    from apps.compras.services import cancelar_orden
    from apps.core.auditoria import auditar
    from apps.recomendaciones.models import RecomendacionCompra

    from .models import ProductoProveedor

    if origen.pk == destino.pk:
        raise ErrorProveedor("Elige un proveedor diferente.")
    if origen.negocio_id != destino.negocio_id:
        raise ErrorProveedor("El proveedor no pertenece a tu negocio.")
    if ordenes not in ("esperar", "cancelar"):
        raise ErrorProveedor("Opción inválida para las órdenes abiertas.")

    with transaction.atomic():
        productos = Producto.objects.filter(negocio=origen.negocio, proveedor_principal=origen)
        if categoria is not None:
            productos = productos.filter(categoria=categoria)
        ids = list(productos.values_list("pk", flat=True))
        # Precio y empaque pactados: si el nuevo proveedor no los tiene, se copian del anterior como punto de partida
        existentes = set(ProductoProveedor.objects.filter(proveedor=destino, producto_id__in=ids)
                         .values_list("producto_id", flat=True))
        viejos = {pp.producto_id: pp for pp in ProductoProveedor.objects.filter(proveedor=origen, producto_id__in=ids)}
        nuevos = []
        for p in productos.only("pk", "precio_compra"):
            if p.pk in existentes:
                continue
            viejo = viejos.get(p.pk)
            nuevos.append(ProductoProveedor(proveedor=destino, producto_id=p.pk,
                                            precio_compra=viejo.precio_compra if viejo else p.precio_compra,
                                            multiplo_empaque=viejo.multiplo_empaque if viejo else 1))
        ProductoProveedor.objects.bulk_create(nuevos)
        Producto.objects.filter(pk__in=ids).update(proveedor_principal=destino)
        recs = RecomendacionCompra.objects.filter(producto_id__in=ids, estado=RecomendacionCompra.Estado.PENDIENTE,
                                                  proveedor=origen).update(proveedor=destino)

        # Una orden que también trae productos que NO cambian de proveedor se deja como está
        from apps.compras.models import DetalleOrdenCompra

        mixtas = DetalleOrdenCompra.objects.filter(orden__proveedor=origen).exclude(producto_id__in=ids).values("orden_id")
        abiertas = (OrdenCompra.objects.filter(proveedor=origen, detalles__producto_id__in=ids)
                    .exclude(pk__in=mixtas).distinct())
        borradores = list(abiertas.filter(estado=OrdenCompra.Estado.BORRADOR))
        for o in borradores:
            o.proveedor = destino
            o.observaciones = (o.observaciones + f"\nPasada de {origen.nombre} por cambio de proveedor.").strip()
            o.save(update_fields=["proveedor", "observaciones", "actualizado"])
        en_camino = list(abiertas.filter(estado__in=[OrdenCompra.Estado.ENVIADA, OrdenCompra.Estado.CONFIRMADA,
                                                     OrdenCompra.Estado.RECIBIDA_PARCIAL]))
        canceladas = 0
        if ordenes == "cancelar":
            for o in en_camino:
                cancelar_orden(o, usuario, f"Cambio de proveedor a {destino.nombre}")
                canceladas += 1

        desactivado = False
        if desactivar and not Producto.objects.filter(proveedor_principal=origen).exists():
            origen.activo = False
            origen.save(update_fields=["activo", "actualizado"])
            desactivado = True

        resultado = {"productos": len(ids), "precios_copiados": len(nuevos), "recomendaciones": recs,
                     "borradores_movidos": len(borradores), "ordenes_en_camino": len(en_camino) - canceladas,
                     "ordenes_canceladas": canceladas, "desactivado": desactivado}
        auditar(origen.negocio, usuario, "reemplazar_proveedor", origen, destino=destino.pk,
                categoria=getattr(categoria, "pk", None), **resultado)
    return resultado
