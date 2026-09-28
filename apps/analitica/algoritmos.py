"""Algoritmos puros (sin Django) del motor inteligente. Ver docs/DISENO.md §6.

Todos son explicables para un pequeño empresario y fáciles de probar con tests unitarios.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import mean, median, pstdev

# ---------------------------------------------------------------- Demanda


def suavizado_exponencial(serie: list[float], alfa: float = 0.3) -> float:
    """Demanda diaria estimada con suavizado exponencial simple.

    Con menos de 7 observaciones devuelve el promedio simple.
    """
    if not serie:
        return 0.0
    if len(serie) < 7:
        return mean(serie)
    nivel = mean(serie[:7])
    for x in serie[7:]:
        nivel = alfa * x + (1 - alfa) * nivel
    return nivel


@dataclass
class Pronostico:
    valor: float
    minimo: float
    maximo: float


def pronostico_holt(serie: list[float], alfa: float = 0.5, beta: float = 0.3, pasos: int = 1) -> Pronostico:
    """Método de Holt (nivel + tendencia) para el próximo período.

    Ej: [30, 35, 42, 48, 51] → ~55–57. Devuelve un rango usando el error medio del ajuste.
    """
    if not serie:
        return Pronostico(0, 0, 0)
    if len(serie) == 1:
        return Pronostico(serie[0], serie[0], serie[0])
    nivel, tendencia = serie[0], serie[1] - serie[0]
    errores = []
    for x in serie[1:]:
        prediccion = nivel + tendencia
        errores.append(abs(x - prediccion))
        nivel_ant = nivel
        nivel = alfa * x + (1 - alfa) * (nivel + tendencia)
        tendencia = beta * (nivel - nivel_ant) + (1 - beta) * tendencia
    valor = max(0.0, nivel + pasos * tendencia)
    error = mean(errores) if errores else 0
    return Pronostico(valor, max(0.0, valor - error), valor + error)


def pronostico_holt_winters(serie: list[float], periodo: int = 12, alfa: float = 0.4, beta: float = 0.1,
                            gamma: float = 0.3) -> Pronostico:
    """Holt-Winters aditivo (nivel + tendencia + estacionalidad). Requiere ≥ 2 temporadas completas.

    Útil para negocios con picos anuales (ropa en diciembre, útiles en enero)."""
    if len(serie) < 2 * periodo:
        return pronostico_holt(serie)
    nivel = mean(serie[:periodo])
    tendencia = (mean(serie[periodo:2 * periodo]) - nivel) / periodo
    estacional = [x - nivel for x in serie[:periodo]]
    errores = []
    for t, x in enumerate(serie):
        s_idx = t % periodo
        prediccion = nivel + tendencia + estacional[s_idx]
        if t >= periodo:
            errores.append(abs(x - prediccion))
        nivel_ant = nivel
        nivel = alfa * (x - estacional[s_idx]) + (1 - alfa) * (nivel + tendencia)
        tendencia = beta * (nivel - nivel_ant) + (1 - beta) * tendencia
        estacional[s_idx] = gamma * (x - nivel) + (1 - gamma) * estacional[s_idx]
    valor = max(0.0, nivel + tendencia + estacional[len(serie) % periodo])
    error = mean(errores) if errores else 0
    return Pronostico(valor, max(0.0, valor - error), valor + error)


def desviacion(serie: list[float]) -> float:
    return pstdev(serie) if len(serie) > 1 else 0.0


# ---------------------------------------------------------------- Reposición


def dias_de_cobertura(stock: float, demanda_diaria: float) -> float | None:
    """¿En cuántos días se agota al ritmo actual? None = no hay ventas."""
    if demanda_diaria <= 0:
        return None
    return stock / demanda_diaria


def stock_seguridad(sigma_d: float, tiempo_entrega: float, stock_minimo: float = 0, z: float = 1.65) -> float:
    """SS = max(stock_minimo, z · σd · √L)."""
    return max(stock_minimo, z * sigma_d * math.sqrt(max(tiempo_entrega, 0)))


def punto_de_reorden(demanda_diaria: float, tiempo_entrega: float, ss: float) -> float:
    return demanda_diaria * tiempo_entrega + ss


def pedido_sugerido(
    *,
    stock: float,
    demanda_diaria: float,
    tiempo_entrega: float,
    horizonte: float,
    ss: float,
    en_transito: float = 0,
    multiplo: int = 1,
) -> int:
    """Pedido = max(0, ⌈d·(L+H) + SS − stock − en_tránsito⌉), redondeado al múltiplo de empaque.

    Ejemplo del enunciado: stock 8, d=5/día (35/semana), L=0, H=7, SS=10 → 37.
    """
    necesario = demanda_diaria * (tiempo_entrega + horizonte) + ss - stock - en_transito
    if necesario <= 0:
        return 0
    cantidad = math.ceil(round(necesario, 2))  # evita pedir 1 unidad extra por decimales
    multiplo = max(1, multiplo)
    return math.ceil(cantidad / multiplo) * multiplo


def tope_por_vida_util(*, demanda_diaria: float, vida_util: float, tiempo_entrega: float, stock: float,
                       en_transito: float = 0) -> int | None:
    """Máximo que conviene pedir de un perecedero: lo que se alcanza a vender antes de que se dañe.

    Lo que ya hay (y lo que viene en camino) se vende primero (FEFO); cuando llega el pedido, lo que quede de eso
    se come parte de la vida útil del pedido nuevo. Ejemplo: d=2/día, vida 4 días, sin stock → máximo 8.
    Devuelve None si el producto no tiene vida útil (no hay tope).
    """
    if not vida_util:
        return None  # no perecedero: sin tope
    if demanda_diaria <= 0:
        return 0
    sobrante_al_llegar = max(0.0, stock + en_transito - demanda_diaria * tiempo_entrega)
    return max(0, math.floor(demanda_diaria * vida_util - sobrante_al_llegar))


# ---------------------------------------------------------------- Rotación y anomalías


def clasificar_rotacion(
    dias_con_venta: int, dias_periodo: int, dias_desde_ultima_venta: int | None, dias_sin_movimiento: int = 45
) -> str:
    """ALTA (≥50 % de días con venta), MEDIA (15–50 %), BAJA (<15 % o sin ventas recientes)."""
    if dias_desde_ultima_venta is None or dias_desde_ultima_venta >= dias_sin_movimiento:
        return "BAJA"
    proporcion = dias_con_venta / dias_periodo if dias_periodo else 0
    if proporcion >= 0.5:
        return "ALTA"
    if proporcion >= 0.15:
        return "MEDIA"
    return "BAJA"


def zscore_robusto(valor: float, historia: list[float]) -> float:
    """z = 0.6745·(x − mediana)/MAD. Resistente a los propios valores atípicos."""
    if len(historia) < 5:
        return 0.0
    med = median(historia)
    mad = median(abs(x - med) for x in historia)
    if mad == 0:
        # historia constante: cualquier desviación relevante es anómala
        mad = max(mean(abs(x - med) for x in historia), 0.1 * abs(med), 1e-9)
    return 0.6745 * (valor - med) / mad


def es_anomalo(valor: float, historia: list[float], umbral: float = 3.5) -> bool:
    return abs(zscore_robusto(valor, historia)) > umbral
