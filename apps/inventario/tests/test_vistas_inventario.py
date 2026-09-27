from decimal import Decimal

from apps.inventario.models import TipoMovimiento
from apps.inventario.services import ErrorInventario, registrar_movimiento
from apps.usuarios.models import Rol, Usuario


def test_registrar_entrada_desde_formulario(client, admin, producto):
    client.force_login(admin)
    resp = client.post("/inventario/", {"producto": producto.pk, "tipo": "ENTRADA_COMPRA", "cantidad": "12",
                                         "costo_unitario": "8000"})
    producto.refresh_from_db()
    assert resp.status_code == 302 and producto.stock_actual == 12 and producto.precio_compra == 8000


def test_salida_sin_motivo_muestra_error(client, admin, producto):
    registrar_movimiento(producto=producto, tipo=TipoMovimiento.ENTRADA_INICIAL, cantidad=5, usuario=admin)
    client.force_login(admin)
    resp = client.post("/inventario/", {"producto": producto.pk, "tipo": "SALIDA_DANADO", "cantidad": "1"})
    assert resp.status_code == 200 and "requiere un motivo" in resp.content.decode()


def test_vendedor_no_registra_movimientos(client, negocio):
    v = Usuario.objects.create_user("v", password="x", negocio=negocio, rol=Rol.VENDEDOR)
    client.force_login(v)
    assert client.get("/inventario/").status_code == 403


def test_kardex_csv(client, admin, producto):
    registrar_movimiento(producto=producto, tipo=TipoMovimiento.ENTRADA_INICIAL, cantidad=5, usuario=admin)
    client.force_login(admin)
    resp = client.get(f"/inventario/kardex/{producto.pk}/?formato=csv")
    assert resp["Content-Type"].startswith("text/csv") and "Inventario inicial" in resp.content.decode("utf-8-sig")


def test_fracciones_solo_si_estan_permitidas(producto, admin):
    config = producto.negocio.config
    config.permite_fracciones = False
    config.save()
    try:
        registrar_movimiento(producto=producto, tipo=TipoMovimiento.ENTRADA_INICIAL, cantidad=Decimal("1.5"), usuario=admin)
        raise AssertionError("debió fallar")
    except ErrorInventario as e:
        assert "enteras" in str(e)
