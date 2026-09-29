from datetime import timedelta

from django.utils import timezone

from apps.alertas.models import Alerta
from apps.alertas.motor import evaluar_producto
from apps.inventario.models import TipoMovimiento as T
from apps.inventario.services import registrar_movimiento
from apps.recomendaciones.services import recomendar_producto
from apps.ventas.services import registrar_venta


def _historial(producto, admin, ventas_por_dia, dias=20):
    registrar_movimiento(
        producto=producto,
        tipo=T.ENTRADA_INICIAL,
        cantidad=ventas_por_dia * dias + 5,
        usuario=admin,
        fecha=timezone.now() - timedelta(days=dias + 1),
        evaluar_alertas=False,
    )
    for i in range(dias, 0, -1):
        registrar_venta(
            negocio=producto.negocio,
            vendedor=admin,
            fecha=timezone.now() - timedelta(days=i),
            lineas=[{"producto": producto, "cantidad": ventas_por_dia}],
        )


def test_riesgo_de_agotamiento_relaciona_ventas_y_proveedor(producto, admin):
    # 5 unidades, vende 3/día, proveedor tarda 4 días → riesgo
    _historial(producto, admin, 3)
    producto.refresh_from_db()
    assert producto.stock_actual == 5
    alertas = evaluar_producto(producto.pk)
    riesgo = [a for a in alertas if a.tipo == Alerta.Tipo.RIESGO_AGOTAMIENTO]
    assert riesgo and riesgo[0].severidad == Alerta.Severidad.ACTUAR
    assert "el proveedor tarda 4 días" in riesgo[0].mensaje


def test_alertas_no_se_duplican(producto, admin):
    _historial(producto, admin, 3)
    evaluar_producto(producto.pk)
    evaluar_producto(producto.pk)
    assert Alerta.objects.filter(producto=producto, tipo=Alerta.Tipo.RIESGO_AGOTAMIENTO).count() == 1


def test_anomalia_en_ventas(producto, admin):
    _historial(producto, admin, 10, dias=10)
    registrar_movimiento(producto=producto, tipo=T.ENTRADA_COMPRA, cantidad=100, usuario=admin, evaluar_alertas=False)
    registrar_venta(negocio=producto.negocio, vendedor=admin, lineas=[{"producto": producto, "cantidad": 47}])
    alertas = evaluar_producto(producto.pk, hoy=timezone.localdate())
    assert any(a.tipo == Alerta.Tipo.ANOMALIA for a in alertas)


def test_vencimiento_proximo(producto, admin):
    registrar_movimiento(
        producto=producto,
        tipo=T.ENTRADA_COMPRA,
        cantidad=12,
        usuario=admin,
        fecha_vencimiento=timezone.localdate() + timedelta(days=3),
        evaluar_alertas=False,
    )
    alertas = evaluar_producto(producto.pk)
    venc = [a for a in alertas if a.tipo == Alerta.Tipo.VENCIMIENTO]
    assert venc and venc[0].severidad == Alerta.Severidad.ACTUAR


def test_recomendacion_explicada(producto, admin):
    _historial(producto, admin, 3)
    rec = recomendar_producto(producto)
    assert rec is not None and rec.cantidad_sugerida > 0
    assert "conviene pedir" in rec.explicacion
