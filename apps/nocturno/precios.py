"""Precios por franja horaria: happy hour, 2×1, noches temáticas."""

from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal


def precios_especiales(negocio, lineas, momento) -> list:
    """(descuento, nombre) por línea, o None. Con 2×1 se juntan las unidades del mismo producto de TODA la cuenta
    pedidas dentro de la franja (cada ronda es una línea distinta: una cerveza ahora y otra en 20 minutos son un par)."""
    from .models import PrecioEspecial

    if not getattr(negocio, "giro", ""):
        return [None] * len(lineas)
    reglas = list(PrecioEspecial.objects.filter(negocio=negocio, activa=True))
    resultado: list = [None] * len(lineas)
    pares: dict = {}  # (regla, producto) → [índices de línea]
    for i, linea in enumerate(lineas):
        if linea.get("cortesia") or linea.get("sin_descuento"):
            continue
        p = linea["producto"]
        cant = Decimal(str(linea["cantidad"]))
        precio = Decimal(str(linea.get("precio_unitario", p.precio_venta)))
        cuando = linea.get("momento") or momento
        for r in reglas:
            if not (r.aplica_a(p) and r.vigente_en(cuando)):
                continue
            if r.tipo == r.Tipo.DOS_POR_UNO:
                pares.setdefault((r.pk, p.pk), []).append(i)
                continue
            desc = descuento_de(r, cant, precio)
            if desc > 0 and (resultado[i] is None or desc > resultado[i][0]):
                resultado[i] = (desc, r.nombre)
    nombres = {r.pk: r.nombre for r in reglas}
    for (regla_pk, _), indices in pares.items():
        total = sum(Decimal(str(lineas[i]["cantidad"])) for i in indices)
        gratis = (total // 2).to_integral_value(rounding=ROUND_DOWN)
        for i in sorted(indices, key=lambda i: Decimal(str(lineas[i].get("precio_unitario",
                                                                           lineas[i]["producto"].precio_venta)))):
            if gratis <= 0:
                break
            linea = lineas[i]
            cant = Decimal(str(linea["cantidad"]))
            precio = Decimal(str(linea.get("precio_unitario", linea["producto"].precio_venta)))
            unidades = min(gratis, cant.to_integral_value(rounding=ROUND_DOWN))
            gratis -= unidades
            desc = unidades * precio
            if desc > 0 and (resultado[i] is None or desc > resultado[i][0]):
                resultado[i] = (desc, nombres[regla_pk])
    return resultado


def descuento_de(regla, cantidad: Decimal, precio: Decimal) -> Decimal:
    bruto = cantidad * precio
    if regla.tipo == regla.Tipo.PORCENTAJE:
        desc = bruto * regla.valor / 100
    elif regla.tipo == regla.Tipo.DOS_POR_UNO:
        desc = (cantidad // 2) * precio  # de cada dos, uno gratis
    else:  # precio fijo
        desc = max(Decimal("0"), (precio - regla.valor) * cantidad)
    return min(bruto, desc.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
