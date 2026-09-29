"""Ejecuta las reglas y persiste alertas deduplicadas (una abierta por producto + tipo)."""

from datetime import date

from django.utils import timezone

from apps.analitica.services import analizar_producto
from apps.catalogo.models import Producto

from .models import Alerta
from .reglas import REGLAS
from .silencio import esta_silenciada

ABIERTAS = [Alerta.Estado.ABIERTA, Alerta.Estado.VISTA]
# Alertas que no dependen del estado actual del producto: solo las cierra una persona
TIPOS_MANUALES = {Alerta.Tipo.ANOMALIA, Alerta.Tipo.VENTA_SIN_STOCK}


def evaluar_producto(producto_id: int, hoy: date | None = None) -> list[Alerta]:
    hoy = hoy or timezone.localdate()
    producto = Producto.objects.select_related("negocio__config", "proveedor_principal").get(pk=producto_id)
    if not producto.activo or not producto.maneja_stock:  # agrupadores y preparados no tienen stock propio
        return []
    analisis = analizar_producto(producto, hoy)
    config = getattr(producto.negocio, "config", None)
    hallazgos = [h for regla in REGLAS for h in regla.evaluar(analisis, hoy)
                 if not esta_silenciada(config, h.tipo, producto.categoria_id)]
    tipos_vigentes = {h.tipo for h in hallazgos}

    # Autoresolver alertas cuya condición ya no se cumple
    Alerta.objects.filter(producto=producto, estado__in=ABIERTAS).exclude(
        tipo__in=tipos_vigentes | TIPOS_MANUALES
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
    for pid in Producto.objects.filter(negocio=negocio, activo=True, es_agrupador=False).exclude(
            tipo="PREPARADO").values_list("pk", flat=True):
        total += len(evaluar_producto(pid, hoy))
    return total


TIPOS_AJUSTE = {"ENTRADA_AJUSTE", "SALIDA_AJUSTE", "SALIDA_DANADO"}


def evaluar_ajuste(movimiento_id: int) -> Alerta | None:
    """Ajustes y bajas inusuales: comparados con el historial de ajustes del producto
    o, sin historia, con el tamaño del stock. Detecta y pide revisión; no acusa."""
    from apps.analitica import algoritmos as alg
    from apps.core.formato import numero
    from apps.inventario.models import Movimiento

    m = Movimiento.objects.select_related("producto", "usuario").get(pk=movimiento_id)
    if m.tipo not in TIPOS_AJUSTE:
        return None
    historia = [float(x) for x in Movimiento.objects.filter(producto=m.producto, tipo__in=TIPOS_AJUSTE)
                .exclude(pk=m.pk).order_by("-fecha").values_list("cantidad", flat=True)[:30]]
    stock_previo = float(m.stock_resultante + (m.cantidad if not m.es_entrada else -m.cantidad))
    cantidad = float(m.cantidad)
    if len(historia) >= 5:
        inusual = alg.es_anomalo(cantidad, historia)
    else:
        inusual = cantidad >= max(5.0, 0.3 * stock_previo)
    if not inusual:
        return None
    Movimiento.objects.filter(pk=m.pk).update(marcado_anomalo=True)  # los movimientos no se editan con save()
    return Alerta.objects.create(
        negocio=m.negocio, producto=m.producto, tipo=Alerta.Tipo.ANOMALIA, severidad=Alerta.Severidad.REVISAR,
        mensaje=(f"Ajuste inusual en {m.producto.nombre}: {m.get_tipo_display().lower()} de {numero(cantidad)} u. "
                 f"por {m.usuario or 'usuario desconocido'} (stock previo {numero(stock_previo)}).")[:300],
        accion_sugerida="Verificar el motivo: " + (m.motivo or "sin motivo")[:150],
        datos={"movimiento": m.pk},
    )
