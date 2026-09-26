"""Ejecuta las reglas y persiste alertas deduplicadas (una abierta por producto + tipo)."""

from datetime import date

from apps.analitica.services import analizar_producto
from apps.catalogo.models import Producto

from .models import Alerta
from .reglas import REGLAS

ABIERTAS = [Alerta.Estado.ABIERTA, Alerta.Estado.VISTA]


def evaluar_producto(producto_id: int, hoy: date | None = None) -> list[Alerta]:
    hoy = hoy or date.today()
    producto = Producto.objects.select_related("negocio__config", "proveedor_principal").get(pk=producto_id)
    if not producto.activo:
        return []
    analisis = analizar_producto(producto, hoy)
    hallazgos = [h for regla in REGLAS for h in regla.evaluar(analisis, hoy)]
    tipos_vigentes = {h.tipo for h in hallazgos}

    # Autoresolver alertas cuya condición ya no se cumple
    Alerta.objects.filter(producto=producto, estado__in=ABIERTAS).exclude(
        tipo__in=tipos_vigentes | {Alerta.Tipo.ANOMALIA}
    ).update(estado=Alerta.Estado.RESUELTA)

    alertas = []
    for h in hallazgos:
        alertas.append(_upsert(producto, h))
    return alertas


def _upsert(producto, h):
    existente = Alerta.objects.filter(producto=producto, tipo=h.tipo, estado__in=ABIERTAS).first()
    campos = dict(severidad=h.severidad, mensaje=h.mensaje[:300], accion_sugerida=h.accion_sugerida, datos=h.datos)
    if existente:
        for k, v in campos.items():
            setattr(existente, k, v)
        existente.save()
        return existente
    return Alerta.objects.create(negocio=producto.negocio, producto=producto, tipo=h.tipo, **campos)


def evaluar_negocio(negocio, hoy: date | None = None) -> int:
    total = 0
    for pid in Producto.objects.filter(negocio=negocio, activo=True).values_list("pk", flat=True):
        total += len(evaluar_producto(pid, hoy))
    return total
