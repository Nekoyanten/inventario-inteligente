"""Apariencia de cada negocio: su color, modo claro/oscuro, letra grande y logo."""

import re

PALETAS = [
    ("#1f7a4d", "Verde"), ("#2563eb", "Azul"), ("#7c3aed", "Morado"), ("#9f1239", "Vino"),
    ("#ea580c", "Naranja"), ("#0f766e", "Turquesa"), ("#db2777", "Rosa"), ("#334155", "Grafito"),
]
COLOR_DEFECTO = "#1f7a4d"
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def _rgb(color: str) -> tuple[int, int, int]:
    color = color if HEX.match(color or "") else COLOR_DEFECTO
    return int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)


def _hex(r, g, b) -> str:
    return "#{:02x}{:02x}{:02x}".format(*(max(0, min(255, round(x))) for x in (r, g, b)))


def _luminancia(r, g, b) -> float:
    def canal(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * canal(r) + 0.7152 * canal(g) + 0.0722 * canal(b)


def tokens(color: str) -> dict:
    """Variables CSS a partir del color del negocio; el texto sobre el color se elige para que siempre se lea."""
    r, g, b = _rgb(color)
    lum = _luminancia(r, g, b)
    # blanco o casi negro: el que dé más contraste (WCAG)
    contraste_blanco = 1.05 / (lum + 0.05)
    contraste_negro = (lum + 0.05) / 0.0592
    # color para texto y enlaces sobre fondo blanco: se oscurece hasta leerse bien (contraste 4.5:1)
    tr, tg, tb = r, g, b
    while 1.05 / (_luminancia(tr, tg, tb) + 0.05) < 4.5 and (tr + tg + tb) > 0:
        tr, tg, tb = tr * 0.9, tg * 0.9, tb * 0.9
    return {
        "texto": _hex(tr, tg, tb),
        "color": _hex(r, g, b),
        "oscuro": _hex(r * 0.82, g * 0.82, b * 0.82),
        "sobre": "#ffffff" if contraste_blanco >= contraste_negro else "#111827",
        "suave": f"rgba({r}, {g}, {b}, 0.10)",
        "foco": f"rgba({r}, {g}, {b}, 0.35)",
    }


def de_negocio(negocio) -> dict:
    config = getattr(negocio, "config", None) if negocio else None
    t = tokens(getattr(config, "color_principal", COLOR_DEFECTO) or COLOR_DEFECTO)
    t.update(tema=getattr(config, "tema", "AUTO") or "AUTO", letra_grande=bool(getattr(config, "letra_grande", False)),
             logo=config.logo if config is not None and getattr(config, "logo", None) else None)
    return t
