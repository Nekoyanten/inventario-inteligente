from datetime import timedelta

import pytest
from django.utils import timezone

from apps.inventario.models import ConteoFisico, DetalleConteo, Lote, Movimiento, TipoMovimiento
from apps.inventario.services import ErrorInventario, aprobar_conteo, kardex, registrar_movimiento

T = TipoMovimiento


def test_entrada_y_salida_actualizan_stock_y_kardex(producto, admin):
    registrar_movimiento(producto=producto, tipo=T.ENTRADA_COMPRA, cantidad=20, usuario=admin, costo_unitario=8000)
    registrar_movimiento(producto=producto, tipo=T.SALIDA_VENTA, cantidad=12, usuario=admin)
    producto.refresh_from_db()
    assert producto.stock_actual == 8
    movs = list(kardex(producto))
    assert [m.stock_resultante for m in movs] == [20, 8]
    assert all(m.usuario == admin for m in movs)


def test_no_permite_stock_negativo(producto, admin):
    with pytest.raises(ErrorInventario):
        registrar_movimiento(producto=producto, tipo=T.SALIDA_VENTA, cantidad=1, usuario=admin)


def test_ajuste_exige_motivo(producto, admin):
    with pytest.raises(ErrorInventario):
        registrar_movimiento(producto=producto, tipo=T.ENTRADA_AJUSTE, cantidad=3, usuario=admin, motivo="")


def test_movimientos_son_inmutables(producto, admin):
    m = registrar_movimiento(producto=producto, tipo=T.ENTRADA_INICIAL, cantidad=5, usuario=admin)[0]
    m.cantidad = 99
    with pytest.raises(ValueError):
        m.save()


def test_salidas_consumen_lotes_fefo(producto, admin):
    hoy = timezone.localdate()
    registrar_movimiento(
        producto=producto, tipo=T.ENTRADA_COMPRA, cantidad=10, usuario=admin, fecha_vencimiento=hoy + timedelta(days=60)
    )
    registrar_movimiento(
        producto=producto, tipo=T.ENTRADA_COMPRA, cantidad=10, usuario=admin, fecha_vencimiento=hoy + timedelta(days=5)
    )
    registrar_movimiento(producto=producto, tipo=T.SALIDA_VENTA, cantidad=12, usuario=admin)
    lotes = {l.fecha_vencimiento: l.cantidad for l in Lote.objects.filter(producto=producto)}
    assert lotes[hoy + timedelta(days=5)] == 0  # el que vence primero sale primero
    assert lotes[hoy + timedelta(days=60)] == 8


def test_conteo_fisico_genera_ajuste_con_motivo(producto, admin):
    registrar_movimiento(producto=producto, tipo=T.ENTRADA_INICIAL, cantidad=50, usuario=admin)
    conteo = ConteoFisico.objects.create(
        negocio=producto.negocio, responsable=admin, estado=ConteoFisico.Estado.PENDIENTE_APROBACION
    )
    DetalleConteo.objects.create(
        conteo=conteo, producto=producto, stock_sistema=50, stock_contado=47, motivo="Producto dañado"
    )
    aprobar_conteo(conteo, admin)
    producto.refresh_from_db()
    assert producto.stock_actual == 47
    ajuste = Movimiento.objects.get(tipo=T.SALIDA_AJUSTE)
    assert ajuste.cantidad == 3 and "Producto dañado" in ajuste.motivo
