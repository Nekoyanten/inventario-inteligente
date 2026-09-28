"""Priorización de la bandeja: pocas alertas, las que importan hoy."""

from apps.analitica.services import clasificacion_abc

from .models import Alerta

ABIERTAS = [Alerta.Estado.ABIERTA, Alerta.Estado.VISTA]
# Estas se agrupan en un resumen semanal en vez de mostrarse una por una
TIPOS_RESUMEN = {Alerta.Tipo.BAJA_ROTACION, Alerta.Tipo.EXCESO}
ORDEN_TIPO = [
    Alerta.Tipo.AGOTADO, Alerta.Tipo.VENCIDO, Alerta.Tipo.STOCK_CRITICO, Alerta.Tipo.RIESGO_AGOTAMIENTO,
    Alerta.Tipo.ANOMALIA, Alerta.Tipo.VENTA_SIN_STOCK, Alerta.Tipo.VENCIMIENTO, Alerta.Tipo.STOCK_BAJO,
    Alerta.Tipo.EXCESO, Alerta.Tipo.BAJA_ROTACION,
]
PESO_ABC = {"A": 0, "B": 1, "C": 2}
CUANTAS_HOY = 10


def prioridad(alerta: Alerta, abc: dict) -> tuple:
    """Menor = más importante: severidad, luego productos que más venden (ABC), luego el tipo."""
    clase = abc.get(alerta.producto_id, "D")
    tipo = ORDEN_TIPO.index(alerta.tipo) if alerta.tipo in ORDEN_TIPO else len(ORDEN_TIPO)
    return (-alerta.severidad, PESO_ABC.get(clase, 3), tipo, -alerta.creado.timestamp())


def bandeja_hoy(negocio, cuantas: int = CUANTAS_HOY) -> dict:
    abiertas = Alerta.objects.filter(negocio=negocio, estado__in=ABIERTAS).select_related("producto__categoria")
    individuales = list(abiertas.exclude(tipo__in=TIPOS_RESUMEN))
    abc = clasificacion_abc(negocio)
    individuales.sort(key=lambda a: prioridad(a, abc))
    resumen = []
    for tipo in (Alerta.Tipo.BAJA_ROTACION, Alerta.Tipo.EXCESO):
        qs = abiertas.filter(tipo=tipo)
        n = qs.count()
        if n:
            valor = sum(float(a.datos.get("valor_inmovilizado", 0)) for a in qs.select_related(None).only("datos"))
            resumen.append({"tipo": tipo, "etiqueta": Alerta.Tipo(tipo).label, "cantidad": n, "valor": valor})
    return {
        "hoy": individuales[:cuantas],
        "restantes": max(0, len(individuales) - cuantas),
        "resumen": resumen,
        "total": abiertas.count(),
    }
