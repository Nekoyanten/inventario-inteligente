"""Pedido sugerido explicado. El sistema sugiere; el empresario decide."""

from collections import defaultdict

from django.db import transaction

from apps.analitica import algoritmos as alg
from apps.analitica.services import analizar_producto, horizonte_compra
from apps.catalogo.models import Producto
from apps.compras.models import DetalleOrdenCompra, OrdenCompra
from apps.core.formato import cantidad_clara, ritmo_claro
from apps.core.formato import numero as _n

from .models import RecomendacionCompra


def _texto_horizonte(horizonte, origen, producto):
    if origen == "ciclo":
        return f"Haces pedidos cada ~{_n(horizonte)} días, así que el pedido cubre {_n(horizonte)} días"
    return f"Para cubrir {_n(horizonte)} días"


def _nota_proveedor(producto, tiempo_entrega, cache: dict | None = None):
    prov = producto.proveedor_principal
    if prov is None:
        return ""
    clave = ("entregas", prov.pk)
    if cache is not None and clave in cache:
        entregas = cache[clave]
    else:
        entregas = prov.entregas_registradas()
        if cache is not None:
            cache[clave] = entregas
    if entregas == 0 and not producto.proveedores.filter(proveedor=prov, tiempo_entrega_dias__isnull=False).exists():
        return (f" Los {_n(tiempo_entrega)} días de entrega son lo que {prov.nombre} prometió: todavía no hay "
                "entregas registradas para comprobarlo.")
    return ""


def _multiplo(producto):
    if producto.proveedor_principal_id:
        pp = producto.proveedores.filter(proveedor_id=producto.proveedor_principal_id).first()
        return pp.multiplo_empaque if pp else 1
    return 1


def _guardar(producto, cantidad, explicacion, demanda, ss, tiempo_entrega, stock, temporada=""):
    rec, _ = RecomendacionCompra.objects.update_or_create(
        producto=producto,
        estado=RecomendacionCompra.Estado.PENDIENTE,
        defaults=dict(
            negocio=producto.negocio,
            proveedor=producto.proveedor_principal,
            cantidad_sugerida=cantidad,
            demanda_diaria=round(demanda, 3),
            stock_seguridad=round(ss, 3),
            tiempo_entrega=tiempo_entrega,
            stock_al_calcular=stock,
            explicacion=explicacion,
            temporada=temporada[:80],
        ),
    )
    return rec


def recomendar_producto(producto: Producto, hoy=None, ciclos: dict | None = None) -> RecomendacionCompra | None:
    a = analizar_producto(producto, hoy)
    horizonte, origen = horizonte_compra(producto, hoy, ciclos)
    # Si se sabe cada cuánto se compra (revisión periódica), hay que pedir si lo que hay no alcanza hasta la
    # PRÓXIMA compra más lo que tarda en llegar; si no, bastaría con el punto de reorden clásico.
    punto = a.punto_reorden + (a.demanda_diaria * horizonte if origen == "ciclo" else 0)
    necesita = a.stock + a.en_transito <= punto or a.stock <= float(producto.stock_minimo)
    pendientes = RecomendacionCompra.objects.filter(producto=producto, estado=RecomendacionCompra.Estado.PENDIENTE)
    if not necesita:
        pendientes.delete()  # ya no hace falta comprar: se retira la sugerencia vieja
        return None

    multiplo = _multiplo(producto)
    cantidad = alg.pedido_sugerido(
        stock=a.stock,
        demanda_diaria=a.demanda_diaria,
        tiempo_entrega=a.tiempo_entrega,
        horizonte=horizonte,
        ss=a.stock_seguridad,
        en_transito=a.en_transito,
        multiplo=multiplo,
    )
    tope = alg.tope_por_vida_util(demanda_diaria=a.demanda_diaria, vida_util=producto.vida_util_dias or 0,
                                  tiempo_entrega=a.tiempo_entrega, stock=a.stock, en_transito=a.en_transito)
    limitado = tope is not None and cantidad > tope
    if limitado:
        cantidad = max(0, (tope // multiplo) * multiplo) if multiplo > 1 and tope >= multiplo else tope
    if cantidad <= 0:
        pendientes.delete()
        return None

    u = producto.unidad.abreviatura if producto.unidad_id else "und"
    explicacion = (
        f"Hay {cantidad_clara(a.stock, u)} de {producto.nombre}. {ritmo_claro(a.demanda_diaria, u)} y el proveedor "
        f"tarda {_n(a.tiempo_entrega)} días. {_texto_horizonte(horizonte, origen, producto)} más una reserva para "
        f"imprevistos de {cantidad_clara(a.stock_seguridad, u)}, conviene pedir {cantidad_clara(cantidad, u)}."
    )
    if limitado:
        explicacion += (f" Se limitó a {cantidad} porque {producto.nombre} dura {producto.vida_util_dias} días: "
                        "pedir más sería botar mercancía.")
    if producto.vida_util_dias and a.tiempo_entrega >= producto.vida_util_dias:
        explicacion += (" El proveedor tarda tanto como lo que dura el producto: pide poco y seguido, o busca "
                        "uno que entregue más rápido.")
    explicacion += _nota_proveedor(producto, a.tiempo_entrega, ciclos)
    if a.en_transito:
        explicacion += f" Ya hay {_n(a.en_transito)} unidades en camino."
    if a.temporada:
        explicacion += (f" Se consideró la temporada «{a.temporada}»: normalmente vendes ~{_n(a.demanda_base)} por día"
                        f" y en esta época se espera ~{_n(a.demanda_diaria)}.")
    return _guardar(producto, cantidad, explicacion, a.demanda_diaria, a.stock_seguridad, a.tiempo_entrega, a.stock,
                    a.temporada)


def recomendar_familia(padre: Producto, hoy=None, ciclos: dict | None = None,
                       recs: dict | None = None) -> list[RecomendacionCompra]:
    """Ropa y similares: completa la curva de tallas de una familia.

    Cada variante se repone con su propia demanda (corregida por los días que estuvo agotada); aquí se agrega lo que
    solo se ve mirando la familia: la participación de cada talla en las ventas y las tallas que se venden pero
    quedaron en cero (curva rota: el cliente que busca talla M no se lleva la L).

    Nota: en el piloto simulado se probó repartir la demanda de la familia con la curva y rindió peor, porque las
    ventas de una talla agotada no se ven (demanda censurada) y la curva la subestima. Por eso la cantidad sigue
    saliendo de cada variante."""
    from apps.analitica.services import curva_variantes, demanda_familia, tiempo_entrega, unidades_en_transito

    recs = recs if recs is not None else {}
    variantes = list(padre.variantes.filter(activo=True).select_related("proveedor_principal", "negocio__config"))
    if len(variantes) < 2:
        return []
    curva = curva_variantes(padre, hoy=hoy)
    d, _ = demanda_familia(padre, hoy)
    nuevas = []
    minimo = 0.5 / len(variantes)  # la talla vende al menos la mitad de lo que le tocaría si todas vendieran igual
    for v in variantes:
        participacion = curva.get(v.pk, 0)
        nota = f" «{v.nombre}» es el {_n(participacion * 100)} % de las ventas de «{padre.nombre}» (curva de tallas)."
        rec = recs.get(v.pk)
        if rec is not None:
            if "curva de tallas" not in rec.explicacion:
                rec.explicacion += nota
                rec.save(update_fields=["explicacion"])
            continue
        if participacion < minimo or float(v.stock_actual) + unidades_en_transito(v) > 0:
            continue
        L = tiempo_entrega(v)
        horizonte, origen = horizonte_compra(v, hoy, ciclos)
        cantidad = max(1, round(d * participacion * (L + horizonte)))
        explicacion = (f"{v.nombre} está agotada y se vende: sin ella la curva de tallas queda rota (quien busca esta "
                       f"talla no se lleva otra). {_texto_horizonte(horizonte, origen, v)} se recomienda pedir "
                       f"{cantidad}." + nota + _nota_proveedor(v, L, ciclos))
        rec = _guardar(v, cantidad, explicacion, d * participacion, 0, L, 0)
        recs[v.pk] = rec
        nuevas.append(rec)
    return nuevas


def generar_recomendaciones(negocio, hoy=None) -> list[RecomendacionCompra]:
    recs, ciclos, por_producto = [], {}, {}
    config = getattr(negocio, "config", None)
    for p in Producto.objects.filter(negocio=negocio, activo=True, es_agrupador=False).exclude(tipo="PREPARADO").select_related(
        "negocio__config", "proveedor_principal"
    ):
        rec = recomendar_producto(p, hoy, ciclos)
        if rec:
            recs.append(rec)
            por_producto[p.pk] = rec
    if config and config.usa_variantes:
        for padre in Producto.objects.filter(negocio=negocio, activo=True, es_agrupador=True).select_related(
                "negocio__config"):
            recs += recomendar_familia(padre, hoy, ciclos, por_producto)
    return recs


@transaction.atomic
def crear_ordenes_desde_recomendaciones(recomendaciones, usuario, cantidades=None, proveedores=None) -> list[OrdenCompra]:
    """Agrupa recomendaciones aceptadas por proveedor y crea una orden en BORRADOR por cada uno.

    cantidades: {rec_id: cantidad editada}; proveedores: {rec_id: Proveedor} para las que no tenían.
    """
    cantidades, proveedores = cantidades or {}, proveedores or {}
    por_proveedor = defaultdict(list)
    for rec in recomendaciones:
        if rec.pk in proveedores:
            rec.proveedor = proveedores[rec.pk]
        if rec.pk in cantidades:
            rec.cantidad_sugerida = cantidades[rec.pk]
        if rec.proveedor_id is None or rec.cantidad_sugerida <= 0:
            continue
        rec.save(update_fields=["proveedor", "cantidad_sugerida"])
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


def descartar(recomendacion: RecomendacionCompra, usuario, motivo: str):
    from apps.core.auditoria import auditar

    recomendacion.estado = RecomendacionCompra.Estado.DESCARTADA
    recomendacion.motivo_descarte = motivo[:200]
    recomendacion.save(update_fields=["estado", "motivo_descarte"])
    auditar(recomendacion.negocio, usuario, "descartar_recomendacion", recomendacion, motivo=motivo)
