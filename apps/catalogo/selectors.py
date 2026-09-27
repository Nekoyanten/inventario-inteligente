"""Consultas de catálogo reutilizables."""

from django.db.models import Case, CharField, F, Q, Value, When

from apps.core.negocio import del_negocio

from .models import EstadoStock, Producto


def productos_con_estado(negocio):
    """Productos vendibles anotados con su estado de stock (semáforo básico)."""
    return (
        del_negocio(negocio, Producto)
        .filter(es_agrupador=False)
        .select_related("categoria", "marca", "unidad", "padre", "negocio__config")
        .annotate(
            estado=Case(
                When(stock_actual__lte=0, then=Value(EstadoStock.AGOTADO)),
                When(stock_actual__lte=F("stock_minimo") / 2, then=Value(EstadoStock.CRITICO)),
                When(stock_actual__lte=F("stock_minimo"), then=Value(EstadoStock.BAJO)),
                default=Value(EstadoStock.NORMAL),
                output_field=CharField(),
            )
        )
    )


def buscar(qs, texto: str):
    texto = (texto or "").strip()
    if not texto:
        return qs
    filtro = Q()
    for palabra in texto.split():
        filtro &= Q(nombre__icontains=palabra) | Q(sku__icontains=palabra) | Q(codigo_barras=palabra) | Q(
            marca__nombre__icontains=palabra
        )
    return qs.filter(filtro)
