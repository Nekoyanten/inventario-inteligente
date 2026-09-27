import pytest
from rest_framework.test import APIClient

from apps.inventario.models import TipoMovimiento
from apps.inventario.services import registrar_movimiento
from apps.usuarios.models import Rol, Usuario


@pytest.fixture
def api(admin):
    c = APIClient()
    resp = c.post("/api/v1/token/", {"username": "admin", "password": "x"})
    c.credentials(HTTP_AUTHORIZATION="Token " + resp.json()["token"])
    return c


def test_sin_token_no_hay_acceso(db):
    assert APIClient().get("/api/v1/productos/").status_code == 401


def test_productos_y_venta_por_api(api, producto, admin):
    registrar_movimiento(producto=producto, tipo=TipoMovimiento.ENTRADA_INICIAL, cantidad=10, usuario=admin)
    datos = api.get("/api/v1/productos/?q=café").json()
    assert datos["count"] == 1 and datos["results"][0]["estado"] == "NORMAL"
    resp = api.post("/api/v1/ventas/", {"lineas": [{"producto": producto.pk, "cantidad": 2}]}, format="json")
    assert resp.status_code == 201 and float(resp.json()["total"]) == 24000
    producto.refresh_from_db()
    assert producto.stock_actual == 8


def test_movimiento_por_api_valida_stock(api, producto):
    resp = api.post("/api/v1/movimientos/", {"producto": producto.pk, "tipo": "SALIDA_DANADO", "cantidad": 5,
                                             "motivo": "Roto"}, format="json")
    assert resp.status_code == 409


def test_vendedor_no_ve_costos_ni_movimientos(negocio, producto):
    Usuario.objects.create_user("v", password="x", negocio=negocio, rol=Rol.VENDEDOR)
    c = APIClient()
    c.login(username="v", password="x")
    assert "precio_compra" not in c.get("/api/v1/productos/").json()["results"][0]
    assert c.get("/api/v1/movimientos/").status_code == 403


def test_resumen_y_esquema(api):
    assert "inventario" in api.get("/api/v1/resumen/").json()
    assert api.get("/api/esquema/").status_code == 200


def test_pwa(client):
    assert client.get("/manifest.webmanifest").json()["short_name"] == "Inventario"
    assert b"caches" in client.get("/sw.js").content
