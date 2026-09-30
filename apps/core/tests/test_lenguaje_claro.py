"""Cantidades y ritmos en palabras que entiende un mesero, un cajero o quien cuenta la bodega."""

import pytest

from apps.core.formato import cantidad_clara, ritmo_claro


@pytest.mark.parametrize("valor, unidad, texto", [
    (3.9, "bot", "3 botellas y 90 % de otra"), (3.5, "bot", "3 botellas y media"), (0.5, "bot", "media botella"),
    (0.25, "bot", "un cuarto de botella"), (0.2, "bot", "20 % de una botella"), (1, "bot", "1 botella"),
    (12, "und", "12 unidades"), (1, "und", "1 unidad"), (0.32, "kg", "320 gramos"), (2.5, "kg", "2,5 kilos"),
    (0.75, "L", "750 ml"), (None, "und", "—"),
])
def test_cantidad_clara(valor, unidad, texto):
    assert cantidad_clara(valor, unidad) == texto


def test_ritmo_claro():
    assert ritmo_claro(10.9, "und") == "Unas 11 unidades al día"
    assert ritmo_claro(0.4, "bot") == "Unas 3 botellas por semana"
    assert ritmo_claro(0.05, "und") == "Unas 2 unidades al mes"
    assert ritmo_claro(0.05, "bot") == "Un tercio de botella por semana"
    assert ritmo_claro(0.01, "und").startswith("Casi no se vende")


def test_kardex_de_botella_en_palabras_y_con_lo_que_se_preparo(client, admin, negocio):
    from apps.catalogo.models import Producto
    from apps.inventario.models import TipoMovimiento
    from apps.inventario.services import registrar_movimiento
    from apps.nocturno import services as noc

    negocio.giro = "BAR"
    negocio.save()
    from apps.core.plantillas import aplicar_plantilla

    aplicar_plantilla(negocio)
    agu = Producto.objects.create(negocio=negocio, sku="AGU", nombre="Aguardiente 750", precio_compra=30000,
                                  precio_venta=90000)
    trago = noc.crear_trago(agu, ml_botella=750, ml_trago=30, precio=7000)
    agu.refresh_from_db()
    registrar_movimiento(producto=agu, tipo=TipoMovimiento.ENTRADA_INICIAL, cantidad=4, usuario=admin)
    c = noc.abrir_cuenta(negocio, admin, nombre="Barra")
    noc.agregar_item(c, trago, 8, admin)
    noc.cobrar(c, admin)
    client.force_login(admin)
    html = client.get(f"/inventario/kardex/{agu.pk}/").content.decode()
    assert "3 botellas y dos tercios" in html  # 4 − 8 × 0,04 = 3,68 ≈ 3 y 2/3
    assert "Se usó para preparar" in html and "Se preparó: 8 × Trago de Aguardiente 750" in html
    assert "Saldo" not in html and "quedaron" in html
    detalle = client.get(f"/productos/{agu.pk}/").content.decode()
    assert "3 botellas y dos tercios" in detalle and "¿Cuánto se vende?" in detalle
