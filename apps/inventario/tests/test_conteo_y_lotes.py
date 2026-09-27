from datetime import date, timedelta

from apps.inventario.models import ConteoFisico, Lote, TipoMovimiento
from apps.inventario.services import registrar_movimiento


def test_conteo_fisico_completo(client, admin, producto):
    registrar_movimiento(producto=producto, tipo=TipoMovimiento.ENTRADA_INICIAL, cantidad=50, usuario=admin)
    client.force_login(admin)
    client.post("/inventario/conteos/")
    conteo = ConteoFisico.objects.get()
    d = conteo.detalles.get()
    # sin motivo no se puede enviar
    resp = client.post(f"/inventario/conteos/{conteo.pk}/", {f"contado-{d.pk}": "47", "accion": "enviar"}, follow=True)
    assert "Falta el motivo" in resp.content.decode()
    client.post(f"/inventario/conteos/{conteo.pk}/", {f"contado-{d.pk}": "47", f"motivo-{d.pk}": "Dañado", "accion": "enviar"})
    client.post(f"/inventario/conteos/{conteo.pk}/", {"accion": "aprobar"})
    producto.refresh_from_db()
    conteo.refresh_from_db()
    assert producto.stock_actual == 47 and conteo.estado == ConteoFisico.Estado.APROBADO


def test_encargado_no_aprueba(client, negocio, producto, admin):
    from apps.usuarios.models import Rol, Usuario

    enc = Usuario.objects.create_user("e", password="x", negocio=negocio, rol=Rol.INVENTARIO)
    client.force_login(enc)
    client.post("/inventario/conteos/")
    conteo = ConteoFisico.objects.get()
    client.post(f"/inventario/conteos/{conteo.pk}/", {"accion": "enviar"})
    client.post(f"/inventario/conteos/{conteo.pk}/", {"accion": "aprobar"})
    conteo.refresh_from_db()
    assert conteo.estado == ConteoFisico.Estado.PENDIENTE_APROBACION


def test_retirar_lote_vencido(client, admin, producto):
    registrar_movimiento(producto=producto, tipo=TipoMovimiento.ENTRADA_COMPRA, cantidad=6, usuario=admin,
                         fecha_vencimiento=date.today() - timedelta(days=2))
    lote = Lote.objects.get()
    client.force_login(admin)
    assert "Vencido" in client.get("/inventario/vencimientos/").content.decode()
    client.post(f"/inventario/vencimientos/{lote.pk}/retirar/")
    producto.refresh_from_db()
    assert producto.stock_actual == 0 and producto.movimientos.filter(tipo=TipoMovimiento.SALIDA_VENCIDO).exists()
