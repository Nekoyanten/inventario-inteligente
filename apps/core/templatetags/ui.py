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


@register.inclusion_tag("parciales/grafico_barras.html")
def grafico_barras(datos, pronostico=None, alto=160, compacto=False):
    """Barras SVG accesibles. `datos`: [{'etiqueta','valor'}]; `pronostico`: objeto con valor/minimo/maximo."""
    serie = list(datos)
    if pronostico is not None and getattr(pronostico, "valor", 0):
        serie = serie + [{"etiqueta": "próx.", "valor": pronostico.valor, "pron": True,
                          "min": pronostico.minimo, "max": pronostico.maximo}]
    maximo = max([d.get("max", d["valor"]) for d in serie] + [1])
    ancho_barra, hueco, alto_util = (14, 4, alto - 30) if compacto else (38, 14, alto - 30)
    barras = []
    for i, d in enumerate(serie):
        h = d["valor"] / maximo * alto_util
        x = 10 + i * (ancho_barra + hueco)
        y = alto - 20 - h
        barra = {"x": x, "y": round(y, 1), "h": round(h, 1), "w": ancho_barra, "etiqueta": d["etiqueta"],
                 "valor": d["valor"], "pron": d.get("pron", False), "cx": x + ancho_barra / 2,
                 "y_texto": round(y - 4, 1), "etiquetar": not compacto or i % 5 == 0 or i == len(serie) - 1,
                 "valor_visible": not compacto}
        if d.get("pron"):
            y_max = alto - 20 - d["max"] / maximo * alto_util
            y_min = alto - 20 - d["min"] / maximo * alto_util
            barra.update(y_max=round(y_max, 1), h_banda=round(y_min - y_max, 1), y_texto=round(y_max - 4, 1))
        barras.append(barra)
    return {"barras": barras, "ancho": 20 + len(serie) * (ancho_barra + hueco), "alto": alto, "base": alto - 20,
            "y_etiqueta": alto - 6}


@register.filter
def get_campo(form, nombre):
    return form[nombre]


@register.filter
def num_input(valor):
    """Valor para <input type=number>: 1.000 → 1 · 2.500 → 2.5 (punto decimal, sin ceros de sobra)."""
    n = _num(valor)
    if n is None:
        return ""
    return format(n.normalize(), "f")
