"""Formato de números para mensajes en español de Colombia: 1.234,5"""


def numero(x: float) -> str:
    x = float(x)
    if abs(x - round(x)) < 1e-9:
        return f"{x:,.0f}".replace(",", ".")
    return f"{x:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")


# ---------------------------------------------------------------- cantidades en palabras (para mesero, cajero, bodega)
UNIDADES = {
    "und": ("unidad", "unidades"), "bot": ("botella", "botellas"), "kg": ("kilo", "kilos"), "g": ("gramo", "gramos"),
    "L": ("litro", "litros"), "ml": ("mililitro", "mililitros"), "m": ("metro", "metros"), "caja": ("caja", "cajas"),
    "paq": ("paquete", "paquetes"), "doc": ("docena", "docenas"), "par": ("par", "pares"),
}
FRACCIONES = [(0.25, "un cuarto"), (1 / 3, "un tercio"), (0.5, "media"), (2 / 3, "dos tercios"), (0.75, "tres cuartos")]


def _nombre_unidad(abrev: str | None, n: float) -> str:
    singular, plural = UNIDADES.get(abrev or "und", (abrev or "unidad", abrev or "unidades"))
    return singular if abs(n - 1) < 1e-9 else plural


def _fraccion(frac: float) -> str:
    for valor, texto in FRACCIONES:
        if abs(frac - valor) <= 0.03:
            return texto
    return f"{round(frac * 100)} %"


def cantidad_clara(valor, abrev: str | None = "und") -> str:
    """Cantidad como la diría una persona: «3 botellas y media», «320 gramos», «12 unidades»."""
    try:
        n = float(valor)
    except (TypeError, ValueError):
        return "—"
    signo, n = ("menos " if n < 0 else ""), abs(n)
    abrev = abrev or "und"
    if abrev == "kg" and 0 < n < 1:
        return f"{signo}{numero(round(n * 1000))} gramos"
    if abrev == "L" and 0 < n < 1:
        return f"{signo}{numero(round(n * 1000))} ml"
    entero, frac = int(n + 1e-9), n - int(n + 1e-9)
    if frac < 0.01:
        return f"{signo}{numero(entero)} {_nombre_unidad(abrev, entero)}"
    if abrev != "bot":  # kilos, litros…: el número con coma basta
        return f"{signo}{numero(n)} {_nombre_unidad(abrev, n)}"
    parte = _fraccion(frac)
    if entero == 0:
        return f"{signo}{parte} botella" if parte in ("media",) else (
            f"{signo}{parte} de botella" if "%" not in parte else f"{signo}{parte} de una botella")
    base = f"{signo}{numero(entero)} {_nombre_unidad(abrev, entero)}"
    return f"{base} y {parte}" if "%" not in parte else f"{base} y {parte} de otra"


def ritmo_claro(por_dia, abrev: str | None = "und") -> str:
    """«Se venden unas 11 unidades al día» / «unas 3 botellas por semana» / «Casi no se vende»."""
    try:
        d = float(por_dia or 0)
    except (TypeError, ValueError):
        return "—"
    if d >= 1:
        n = round(d)
        return f"Unas {numero(n)} {_nombre_unidad(abrev, n)} al día"
    semana = d * 7
    if semana >= 1:
        n = round(semana) if semana >= 2 else round(semana, 1)
        return f"Unas {numero(n)} {_nombre_unidad(abrev, n)} por semana"
    if abrev == "bot" and semana >= 0.05:  # botellas que se sirven por tragos: fracción por semana
        texto = cantidad_clara(semana, "bot")
        return f"{texto[0].upper()}{texto[1:]} por semana"
    mes = d * 30
    if mes >= 1:
        n = round(mes)
        return f"Unas {numero(n)} {_nombre_unidad(abrev, n)} al mes"
    return "Casi no se vende (menos de 1 al mes)"
