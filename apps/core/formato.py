"""Formato de números para mensajes en español de Colombia: 1.234,5"""


def numero(x: float) -> str:
    x = float(x)
    if abs(x - round(x)) < 1e-9:
        return f"{x:,.0f}".replace(",", ".")
    return f"{x:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")
