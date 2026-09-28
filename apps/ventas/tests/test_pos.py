import json

from apps.analitica.models import DemandaDiaria
from apps.inventario.models import TipoMovimiento
from apps.inventario.services import registrar_movimiento
from apps.usuarios.models import Rol, Usuario
from apps.ventas.models import Venta


def _vender(client, producto, cantidad):
    return client.post("/ventas/registrar/", json.dumps({"lineas": [{"producto": producto.pk, "cantidad": cantidad}],
                                                         "medio_pago": "EFECTIVO"}), content_type="application/json")


def test_pos_registra_venta_y_descuenta(client, admin, producto):
    registrar_movimiento(producto=producto, tipo=TipoMovimiento.ENTRADA_INICIAL, cantidad=10, usuario=admin)
    client.force_login(admin)
    resp = _vender(client, producto, 3)
    assert resp.status_code == 200
    producto.refresh_from_db()
    assert producto.stock_actual == 7 and Venta.objects.get(pk=resp.json()["venta"]).total == 36000


def test_pos_sin_stock_responde_409_si_el_negocio_no_lo_permite(client, admin, producto):
    producto.negocio.config.permite_venta_sin_stock = False
    producto.negocio.config.save()
    client.force_login(admin)
    resp = _vender(client, producto, 1)
    assert resp.status_code == 409 and "Stock insuficiente" in resp.json()["error"]


def test_pos_sin_stock_vende_y_deja_ajuste_si_el_negocio_lo_permite(client, admin, producto):
    client.force_login(admin)
    resp = _vender(client, producto, 1)
    assert resp.status_code == 200
    producto.refresh_from_db()
    assert producto.stock_actual == 0


def test_anular_venta_devuelve_inventario_y_demanda(client, admin, producto):
    registrar_movimiento(producto=producto, tipo=TipoMovimiento.ENTRADA_INICIAL, cantidad=10, usuario=admin)
    client.force_login(admin)
    venta_id = _vender(client, producto, 4).json()["venta"]
    client.post(f"/ventas/{venta_id}/anular/", {"motivo": "Error de digitación"})
    producto.refresh_from_db()
    assert producto.stock_actual == 10 and Venta.objects.get(pk=venta_id).estado == Venta.Estado.ANULADA
    assert sum(d.cantidad for d in DemandaDiaria.objects.filter(producto=producto)) == 0


def test_vendedor_solo_ve_sus_ventas(client, admin, producto):
    registrar_movimiento(producto=producto, tipo=TipoMovimiento.ENTRADA_INICIAL, cantidad=10, usuario=admin)
    client.force_login(admin)
    venta_admin = _vender(client, producto, 1).json()["venta"]
    vendedor = Usuario.objects.create_user("v", password="x", negocio=producto.negocio, rol=Rol.VENDEDOR)
    client.force_login(vendedor)
    assert client.get(f"/ventas/{venta_admin}/").status_code == 404
    assert client.post(f"/ventas/{venta_admin}/anular/", {"motivo": "x"}).status_code == 403
