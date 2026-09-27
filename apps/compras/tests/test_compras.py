from datetime import date, timedelta

import pytest
from django.utils import timezone

from apps.compras.models import OrdenCompra
from apps.inventario.models import Lote


@pytest.fixture
def orden(client, admin, producto, proveedor):
    client.force_login(admin)
    resp = client.post("/compras/nueva/", {"proveedor": proveedor.pk, "lineas-producto": [producto.pk],
                                           "lineas-cantidad": ["24"], "lineas-costo": ["8000"]})
    assert resp.status_code == 302
    return OrdenCompra.objects.get()


def test_flujo_completo_de_orden(client, orden, producto):
    assert orden.estado == OrdenCompra.Estado.BORRADOR and orden.total == 24 * 8000
    client.post(f"/compras/{orden.pk}/enviar/")
    client.post(f"/compras/{orden.pk}/confirmar/")
    detalle = orden.detalles.get()
    venc = (date.today() + timedelta(days=40)).isoformat()
    client.post(f"/compras/{orden.pk}/recibir/", {f"recibido-{detalle.pk}": "10", f"vencimiento-{detalle.pk}": venc})
    orden.refresh_from_db()
    producto.refresh_from_db()
    assert orden.estado == OrdenCompra.Estado.RECIBIDA_PARCIAL and producto.stock_actual == 10
    assert Lote.objects.get(producto=producto).fecha_vencimiento.isoformat() == venc
    client.post(f"/compras/{orden.pk}/recibir/", {f"recibido-{detalle.pk}": "14"})
    orden.refresh_from_db()
    producto.refresh_from_db()
    assert orden.estado == OrdenCompra.Estado.RECIBIDA and producto.stock_actual == 24 and orden.dias_entrega == 0


def test_no_recibe_mas_de_lo_pedido(client, orden, producto):
    client.post(f"/compras/{orden.pk}/enviar/")
    detalle = orden.detalles.get()
    resp = client.post(f"/compras/{orden.pk}/recibir/", {f"recibido-{detalle.pk}": "30"}, follow=True)
    assert "más de lo pedido" in resp.content.decode()
    producto.refresh_from_db()
    assert producto.stock_actual == 0


def test_pdf_y_whatsapp(client, orden, proveedor):
    proveedor.whatsapp = "573001234567"
    proveedor.save()
    assert client.get(f"/compras/{orden.pk}/pdf/").content[:4] == b"%PDF"
    assert "wa.me/573001234567" in client.get(f"/compras/{orden.pk}/").content.decode()


def test_compra_directa_ingresa_inventario(client, admin, producto, proveedor):
    client.force_login(admin)
    client.post("/compras/factura/", {"proveedor": proveedor.pk, "numero_factura": "F-12",
                                      "lineas-producto": [producto.pk], "lineas-cantidad": ["5"], "lineas-costo": ["9000"],
                                      "lineas-vencimiento": [""]})
    producto.refresh_from_db()
    orden = OrdenCompra.objects.get()
    assert producto.stock_actual == 5 and producto.precio_compra == 9000
    assert orden.es_compra_directa and orden.estado == OrdenCompra.Estado.RECIBIDA and orden.dias_entrega is None


def test_desempeno_proveedor(client, orden, proveedor):
    from apps.proveedores.services import desempeno

    client.post(f"/compras/{orden.pk}/enviar/")
    OrdenCompra.objects.filter(pk=orden.pk).update(fecha_envio=timezone.now() - timedelta(days=6))
    detalle = orden.detalles.get()
    client.post(f"/compras/{orden.pk}/recibir/", {f"recibido-{detalle.pk}": "24"})
    ind = desempeno(proveedor)
    assert ind["tiempo_promedio"] == 6 and ind["cumplimiento_pct"] == 0  # prometió 4 días


def test_cancelar(client, orden):
    client.post(f"/compras/{orden.pk}/cancelar/", {"motivo": "Ya no se necesita"})
    orden.refresh_from_db()
    assert orden.estado == OrdenCompra.Estado.CANCELADA
