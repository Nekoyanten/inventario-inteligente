"""Pruebas de los algoritmos con los ejemplos exactos del enunciado."""

import pytest

from apps.analitica import algoritmos as alg


def test_pedido_sugerido_ejemplo_cafe():
    # Stock 8, demanda 35/semana, stock de seguridad 10 → 37
    assert alg.pedido_sugerido(stock=8, demanda_diaria=5, tiempo_entrega=0, horizonte=7, ss=10) == 37


def test_pedido_sugerido_redondea_a_multiplo_de_empaque():
    assert alg.pedido_sugerido(stock=8, demanda_diaria=5, tiempo_entrega=0, horizonte=7, ss=10, multiplo=12) == 48


def test_pedido_sugerido_descuenta_en_transito_y_no_es_negativo():
    assert alg.pedido_sugerido(stock=8, demanda_diaria=5, tiempo_entrega=0, horizonte=7, ss=10, en_transito=40) == 0


def test_riesgo_agotamiento_10_unidades_5_por_dia():
    assert alg.dias_de_cobertura(10, 5) == 2


def test_cobertura_sin_ventas_es_none():
    assert alg.dias_de_cobertura(10, 0) is None


def test_pronostico_holt_serie_creciente():
    p = alg.pronostico_holt([30, 35, 42, 48, 51])
    assert 53 <= p.valor <= 60
    assert p.minimo <= p.valor <= p.maximo


def test_anomalia_detecta_47_frente_a_historial_normal():
    historia = [10, 12, 9, 11, 10]
    assert alg.es_anomalo(47, historia)
    assert not alg.es_anomalo(11, historia)


def test_anomalia_requiere_historial_minimo():
    assert not alg.es_anomalo(47, [10, 12])


@pytest.mark.parametrize(
    "dias_venta,ultima,esperado",
    [(20, 1, "ALTA"), (8, 2, "MEDIA"), (2, 3, "BAJA"), (20, 60, "BAJA"), (0, None, "BAJA")],
)
def test_clasificar_rotacion(dias_venta, ultima, esperado):
    assert alg.clasificar_rotacion(dias_venta, 28, ultima, 45) == esperado


def test_stock_seguridad_nunca_menor_al_minimo():
    assert alg.stock_seguridad(sigma_d=0, tiempo_entrega=4, stock_minimo=10) == 10
    assert alg.stock_seguridad(sigma_d=4, tiempo_entrega=4, stock_minimo=0) == pytest.approx(13.2)


def test_suavizado_con_poca_historia_usa_promedio():
    assert alg.suavizado_exponencial([2, 4]) == 3
