"""Análisis de clientes: quién compra, cada cuánto vuelve, quién se está yendo (RFM) y qué opinan."""

from collections import defaultdict
from datetime import datetime, timedelta
from statistics import median

from django.db.models import Avg, Count, Sum
from django.utils import timezone

from .models import Cliente, Encuesta, EnvioOferta, Oferta

SEGMENTOS = {
    "CAMPEON": ("🏆 Campeones", "Compran seguido, hace poco y gastan más. Cuídalos: son la base del negocio."),
    "LEAL": ("💛 Leales", "Vuelven con regularidad."),
    "NUEVO": ("🌱 Nuevos", "Primera compra hace menos de 30 días. La segunda visita es la más difícil."),
    "OCASIONAL": ("🙂 Ocasionales", "Compran de vez en cuando."),
    "EN_RIESGO": ("⚠️ En riesgo", "Venían seguido y ya se demoraron más de lo normal en volver."),
    "PERDIDO": ("💤 Dormidos", "No compran hace más de 90 días."),
}


def _inicio(dia):
    return timezone.make_aware(datetime(dia.year, dia.month, dia.day))


def _clasificar(n: int, recencia: int | None, intervalo: float | None, antiguedad: int | None) -> str:
    if recencia is None:
        return "NUEVO"
    if recencia > 90:
        return "PERDIDO"
    if n >= 2 and intervalo and recencia > max(30, 2 * intervalo):
        return "EN_RIESGO"
    if n <= 1:
        return "NUEVO" if (antiguedad or 0) <= 30 else "OCASIONAL"
    if n >= 6 and recencia <= max(14, (intervalo or 14)):
        return "CAMPEON"
    if n >= 3:
        return "LEAL"
    return "OCASIONAL"


def _fechas_por_cliente(negocio, desde, cliente=None):
    from apps.ventas.models import Venta

    qs = Venta.objects.filter(negocio=negocio, estado=Venta.Estado.COMPLETADA, cliente_ref__isnull=False,
                              fecha__gte=desde)
    if cliente is not None:
        qs = qs.filter(cliente_ref=cliente)
    fechas = defaultdict(list)
    for cid, f in qs.values_list("cliente_ref", "fecha").order_by("fecha"):
        fechas[cid].append(timezone.localdate(f))
    return fechas


def rfm(negocio, hoy=None) -> list[dict]:
    """Una fila por cliente activo: recencia, frecuencia (180 días), monto (180 días), intervalo y segmento."""
    from apps.ventas.models import Venta

    hoy = hoy or timezone.localdate()
    desde = hoy - timedelta(days=365)
    fechas = _fechas_por_cliente(negocio, _inicio(desde))
    montos = dict(Venta.objects.filter(negocio=negocio, estado=Venta.Estado.COMPLETADA, cliente_ref__isnull=False,
                                       fecha__date__gte=hoy - timedelta(days=180))
                  .values("cliente_ref").annotate(t=Sum("total")).values_list("cliente_ref", "t"))
    filas = []
    for c in Cliente.objects.filter(negocio=negocio, activo=True):
        fs = fechas.get(c.pk, [])
        dias = sorted(set(fs))
        brechas = [(b - a).days for a, b in zip(dias, dias[1:], strict=False)]
        intervalo = median(brechas) if brechas else None
        recencia = (hoy - dias[-1]).days if dias else None
        antiguedad = (hoy - dias[0]).days if dias else None
        n180 = sum(1 for f in fs if f >= hoy - timedelta(days=180))
        filas.append({"cliente": c, "recencia": recencia, "frecuencia": n180, "monto": float(montos.get(c.pk) or 0),
                      "intervalo": intervalo, "segmento": _clasificar(len(set(fs)), recencia, intervalo, antiguedad)})
    return filas


def segmento_rfm(cliente: Cliente, hoy=None) -> str:
    hoy = hoy or timezone.localdate()
    desde = hoy - timedelta(days=365)
    fs = _fechas_por_cliente(cliente.negocio, _inicio(desde),
                             cliente).get(cliente.pk, [])
    dias = sorted(set(fs))
    brechas = [(b - a).days for a, b in zip(dias, dias[1:], strict=False)]
    return _clasificar(len(dias), (hoy - dias[-1]).days if dias else None, median(brechas) if brechas else None,
                       (hoy - dias[0]).days if dias else None)


def clientes_por_segmento(negocio, segmentos, hoy=None) -> list[Cliente]:
    return [f["cliente"] for f in rfm(negocio, hoy) if f["segmento"] in segmentos]


def productos_favoritos(cliente: Cliente, n: int = 5):
    from apps.ventas.models import DetalleVenta, Venta

    return list(DetalleVenta.objects.filter(venta__cliente_ref=cliente, venta__estado=Venta.Estado.COMPLETADA)
                .values("producto_id", "producto__nombre").annotate(veces=Count("venta", distinct=True),
                                                                    unidades=Sum("cantidad"))
                .order_by("-veces", "-unidades")[:n])


def satisfaccion(negocio, dias: int = 90, hoy=None) -> dict:
    hoy = hoy or timezone.localdate()
    qs = Encuesta.objects.filter(negocio=negocio, respondida__isnull=False,
                                 respondida__date__gte=hoy - timedelta(days=dias))
    agg = qs.aggregate(promedio=Avg("calificacion"), n=Count("id"))
    enviadas = Encuesta.objects.filter(negocio=negocio, creada__date__gte=hoy - timedelta(days=dias)).count()
    return {"promedio": round(agg["promedio"], 1) if agg["promedio"] else None, "respuestas": agg["n"],
            "tasa_respuesta": round(100 * agg["n"] / enviadas) if enviadas else None,
            "comentarios": list(qs.exclude(comentario="").select_related("cliente", "venta")[:10]),
            "bajas": qs.filter(calificacion__lte=3).count()}


def resumen(negocio, hoy=None) -> dict:
    """Números del panel de clientes."""
    from apps.ventas.models import Venta

    hoy = hoy or timezone.localdate()
    filas = rfm(negocio, hoy)
    por_segmento = defaultdict(list)
    for f in filas:
        por_segmento[f["segmento"]].append(f)
    ventas90 = Venta.objects.filter(negocio=negocio, estado=Venta.Estado.COMPLETADA,
                                    fecha__date__gte=hoy - timedelta(days=90))
    con = ventas90.filter(cliente_ref__isnull=False).aggregate(n=Count("id"), t=Sum("total"))
    sin = ventas90.filter(cliente_ref__isnull=True).aggregate(n=Count("id"), t=Sum("total"))
    activos = [f for f in filas if f["recencia"] is not None and f["recencia"] <= 90]
    recurrentes = [f for f in activos if f["frecuencia"] >= 2]
    intervalos = [f["intervalo"] for f in filas if f["intervalo"]]
    total_ventas = (con["n"] or 0) + (sin["n"] or 0)
    return {
        "clientes": len(filas),
        "activos": len(activos),
        "recurrentes_pct": round(100 * len(recurrentes) / len(activos)) if activos else None,
        "ventas_identificadas_pct": round(100 * (con["n"] or 0) / total_ventas) if total_ventas else None,
        "ticket_con_cliente": (con["t"] or 0) / con["n"] if con["n"] else None,
        "ticket_sin_cliente": (sin["t"] or 0) / sin["n"] if sin["n"] else None,
        "vuelven_cada": round(median(intervalos)) if intervalos else None,
        "segmentos": [{"clave": k, "nombre": SEGMENTOS[k][0], "ayuda": SEGMENTOS[k][1],
                       "cantidad": len(por_segmento.get(k, [])),
                       "monto": sum(f["monto"] for f in por_segmento.get(k, []))} for k in SEGMENTOS],
        "en_riesgo": sorted(por_segmento.get("EN_RIESGO", []), key=lambda f: -f["monto"])[:10],
        "top": sorted(filas, key=lambda f: -f["monto"])[:10],
        "cumpleanos": list(Cliente.objects.filter(negocio=negocio, activo=True, fecha_nacimiento__month=hoy.month)
                           .order_by("fecha_nacimiento__day")),
        "satisfaccion": satisfaccion(negocio, hoy=hoy),
    }


def efectividad(oferta: Oferta) -> dict:
    """¿Sirvió la oferta? Cuántos de los contactados volvieron a comprar mientras estuvo vigente."""
    from apps.ventas.models import Venta

    envios = list(EnvioOferta.objects.filter(oferta=oferta).select_related("cliente"))
    volvieron = 0
    for e in envios:
        if Venta.objects.filter(cliente_ref=e.cliente, estado=Venta.Estado.COMPLETADA, fecha__gte=e.fecha,
                                fecha__date__lte=oferta.hasta).exists():
            volvieron += 1
    usadas = Venta.objects.filter(detalles__oferta=oferta, estado=Venta.Estado.COMPLETADA).distinct()
    agg = usadas.aggregate(n=Count("id"), t=Sum("total"))
    return {"enviados": len(envios), "volvieron": volvieron,
            "retorno_pct": round(100 * volvieron / len(envios)) if envios else None,
            "ventas_con_oferta": agg["n"] or 0, "ingreso": agg["t"] or 0}
