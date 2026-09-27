from apps.dashboard.selectors import resumen_negocio
from apps.inventario.models import TipoMovimiento as T
from apps.inventario.services import registrar_movimiento
from apps.ventas.services import registrar_venta


def test_resumen_negocio(producto, admin):
    registrar_movimiento(producto=producto, tipo=T.ENTRADA_INICIAL, cantidad=10, usuario=admin)
    registrar_venta(negocio=producto.negocio, vendedor=admin, lineas=[{"producto": producto, "cantidad": 4}])
    r = resumen_negocio(producto.negocio)
    assert r["inventario"]["productos"] == 1
    assert r["inventario"]["stock_bajo"] == 1  # 6 ≤ mínimo 8
    assert r["ventas"]["mes"] == 48000


def test_visitante_ve_la_pagina_de_inicio(client):
    resp = client.get("/")
    assert resp.status_code == 200 and "Pruébalo gratis" in resp.content.decode()


def test_dashboard_carga(client, admin, producto):
    client.force_login(admin)
    resp = client.get("/")
    assert resp.status_code == 200 and "¿Cómo está mi negocio?" in resp.content.decode()


def test_exportar_inventario_excel(client, admin, producto):
    client.force_login(admin)
    resp = client.get("/reportes/inventario-actual.xlsx")
    assert resp.status_code == 200 and resp["Content-Type"].startswith("application/vnd.openxml")
