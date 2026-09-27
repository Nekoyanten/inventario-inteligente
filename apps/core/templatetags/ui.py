"""Filtros de presentación compartidos:  {% load ui %}"""

from decimal import Decimal, InvalidOperation

from django import template
from django.utils.html import format_html

register = template.Library()


def _num(valor):
    try:
        return Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError):
        return None


@register.filter
def moneda(valor):
    """1234567.5 → $1.234.568"""
    n = _num(valor)
    if n is None:
        return "—"
    return "$" + f"{n:,.0f}".replace(",", ".")


@register.filter
def cantidad(valor):
    """12.000 → 12 · 2.500 → 2,5"""
    n = _num(valor)
    if n is None:
        return "—"
    if n == n.to_integral_value():
        return f"{n:,.0f}".replace(",", ".")
    return f"{n:,.2f}".rstrip("0").replace(",", "X").replace(".", ",").replace("X", ".")


@register.filter
def porcentaje(valor, decimales=0):
    n = _num(valor)
    return "—" if n is None else f"{n:.{int(decimales)}f} %"


ESTADOS = {
    "AGOTADO": ("gris", "Agotado"),
    "CRITICO": ("rojo", "Crítico"),
    "BAJO": ("amarillo", "Bajo"),
    "NORMAL": ("verde", "Normal"),
    "EXCESO": ("azul", "Exceso"),
    "ALTA": ("verde", "Alta"),
    "MEDIA": ("amarillo", "Media"),
    "BAJA": ("rojo", "Baja"),
}


@register.filter
def insignia(estado):
    """Pastilla de color para estados de stock y rotación."""
    color, texto = ESTADOS.get(str(estado), ("gris", str(estado)))
    return format_html('<span class="insignia {}">{}</span>', color, texto)


@register.simple_tag(takes_context=True)
def url_con(context, **kwargs):
    """Conserva los parámetros GET actuales cambiando algunos (paginación con filtros)."""
    params = context["request"].GET.copy()
    for k, v in kwargs.items():
        params[k] = v
    return "?" + params.urlencode()
