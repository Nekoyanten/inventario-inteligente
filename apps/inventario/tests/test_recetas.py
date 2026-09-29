"""Insumos y recetas: preparados que gastan insumos al venderse y producción propia."""

from decimal import Decimal

import pytest

from apps.analitica.models import DemandaDiaria
from apps.catalogo.models import Producto, RecetaItem, TipoProducto
from apps.core.models import Negocio
from apps.inventario.models import Movimiento, TipoMovimiento
from apps.inventario.recetas import costo_receta, disponibilidad, guardar_item_receta, registrar_produccion
from apps.inventario.services import ErrorInventario, registrar_movimiento
from apps.ventas.services import anular_venta, registrar_venta

pytestmark = pytest.mark.django_db


@pytest.fixture
def cocina(negocio, admin):
    arroz = Producto.objects.create(negocio=negocio, sku="ARROZ", nombre="Arroz", tipo=TipoProducto.INSUMO,
                                    precio_compra=4000)  # por kg
    pollo = Producto.objects.create(negocio=negocio, sku="POLLO", nombre="Pollo", tipo=TipoProducto.INSUMO,
                                    precio_compra=15000)
    almuerzo = Producto.objects.create(negocio=negocio, sku="ALM", nombre="Almuerzo", tipo=TipoProducto.PREPARADO,
                                       precio_venta=18000)
    registrar_movimiento(producto=arroz, tipo=TipoMovimiento.ENTRADA_INICIAL, cantidad=10, usuario=admin)
    registrar_movimiento(producto=pollo, tipo=TipoMovimiento.ENTRADA_INICIAL, cantidad=2, usuario=admin)
    guardar_item_receta(almuerzo, arroz, "0.15")
    guardar_item_receta(almuerzo, pollo, "0.2", merma_pct=10)  # 0,22 kg con la merma
    for p in (arroz, pollo, almuerzo):
        p.refresh_from_db()
    return arroz, pollo, almuerzo


def test_costo_y_disponibilidad_de_la_receta(cocina):
    arroz, pollo, almuerzo = cocina
    assert costo_receta(almuerzo) == Decimal("3900.00")  # 0,15 × 4.000 + 0,22 × 15.000
    assert almuerzo.precio_compra == Decimal("3900.00")
    assert disponibilidad(almuerzo) == 9  # el pollo alcanza para 2 / 0,22 = 9 almuerzos


def test_vender_un_preparado_descuenta_sus_insumos(negocio, admin, cocina):
    arroz, pollo, almuerzo = cocina
    venta = registrar_venta(negocio=negocio, vendedor=admin, lineas=[{"producto": almuerzo, "cantidad": 3}])
    arroz.refresh_from_db()
    pollo.refresh_from_db()
    assert arroz.stock_actual == Decimal("9.55") and pollo.stock_actual == Decimal("1.34")
    detalle = venta.detalles.get()
    assert detalle.costo_unitario == Decimal("3900.00") and detalle.utilidad == 3 * (18000 - 3900)
    assert Movimiento.objects.filter(tipo=TipoMovimiento.SALIDA_INSUMO, referencia_id=venta.pk).count() == 2
    # la demanda del insumo alimenta «Qué comprar» y la del plato, los reportes de ventas
    assert DemandaDiaria.objects.get(producto=pollo).cantidad == Decimal("0.66")
    assert DemandaDiaria.objects.get(producto=almuerzo).cantidad == 3


def test_anular_devuelve_los_insumos(negocio, admin, cocina):
    arroz, pollo, almuerzo = cocina
    venta = registrar_venta(negocio=negocio, vendedor=admin, lineas=[{"producto": almuerzo, "cantidad": 2}])
    anular_venta(venta, admin, "Se canceló el pedido")
    pollo.refresh_from_db()
    assert pollo.stock_actual == 2 and DemandaDiaria.objects.get(producto=pollo).cantidad == 0


def test_sin_insumos_suficientes(negocio, admin, cocina):
    arroz, pollo, almuerzo = cocina
    negocio.config.permite_venta_sin_stock = False
    negocio.config.save()
    with pytest.raises(ErrorInventario, match="Pollo"):
        registrar_venta(negocio=negocio, vendedor=admin, lineas=[{"producto": almuerzo, "cantidad": 10}])
    negocio.config.permite_venta_sin_stock = True
    negocio.config.save()
    registrar_venta(negocio=negocio, vendedor=admin, lineas=[{"producto": almuerzo, "cantidad": 10}])
    pollo.refresh_from_db()
    assert pollo.stock_actual == 0  # se ajustó lo que faltaba y quedó alerta para revisar


def test_los_insumos_no_se_venden_y_los_preparados_no_tienen_stock(negocio, admin, cocina):
    arroz, _, almuerzo = cocina
    with pytest.raises(ErrorInventario, match="insumo"):
        registrar_venta(negocio=negocio, vendedor=admin, lineas=[{"producto": arroz, "cantidad": 1}])
    with pytest.raises(ErrorInventario, match="preparado"):
        registrar_movimiento(producto=almuerzo, tipo=TipoMovimiento.ENTRADA_AJUSTE, cantidad=1, motivo="x")


def test_busqueda_segun_para_que(client, admin, cocina):
    client.force_login(admin)
    venta = {p["nombre"]: p for p in client.get("/productos/buscar.json?q=a&para=venta").json()["resultados"]}
    stock = {p["nombre"] for p in client.get("/productos/buscar.json?q=o&para=stock").json()["resultados"]}
    assert "Arroz" not in venta and venta["Almuerzo"]["stock"] == 9
    assert "Almuerzo" not in stock and {"Arroz", "Pollo"} <= stock


def test_produccion_propia(negocio, admin):
    harina = Producto.objects.create(negocio=negocio, sku="HAR", nombre="Harina", tipo=TipoProducto.INSUMO,
                                     precio_compra=3000)
    pan = Producto.objects.create(negocio=negocio, sku="PAN", nombre="Pan", precio_venta=800)
    registrar_movimiento(producto=harina, tipo=TipoMovimiento.ENTRADA_INICIAL, cantidad=5, usuario=admin)
    guardar_item_receta(pan, harina, "0.05")
    with pytest.raises(ErrorInventario, match="No alcanzan"):
        registrar_produccion(pan, 200, admin)
    registrar_produccion(pan, 40, admin)
    pan.refresh_from_db()
    harina.refresh_from_db()
    assert pan.stock_actual == 40 and harina.stock_actual == 3 and pan.precio_compra == 150
    assert Movimiento.objects.get(producto=pan).tipo == TipoMovimiento.ENTRADA_PRODUCCION


def test_validaciones_de_receta(negocio, cocina):
    arroz, pollo, almuerzo = cocina
    otro = Producto.objects.create(negocio=Negocio.objects.create(nombre="Otro"), sku="X", nombre="Ajeno")
    for insumo in (almuerzo, otro):
        with pytest.raises(ErrorInventario):
            guardar_item_receta(almuerzo, insumo, 1)
    with pytest.raises(ErrorInventario):
        guardar_item_receta(arroz, pollo, 1)  # un insumo no lleva receta
    with pytest.raises(ErrorInventario):
        guardar_item_receta(almuerzo, arroz, 0)


def test_el_costo_del_plato_sigue_al_precio_de_los_insumos(negocio, admin, cocina):
    arroz, pollo, almuerzo = cocina
    registrar_movimiento(producto=pollo, tipo=TipoMovimiento.ENTRADA_COMPRA, cantidad=1, costo_unitario=20000)
    almuerzo.refresh_from_db()
    assert almuerzo.precio_compra == Decimal("5000.00")  # 600 + 0,22 × 20.000


def test_los_preparados_no_generan_alertas_ni_compras_ni_conteos(negocio, admin, cocina):
    from apps.alertas.models import Alerta
    from apps.alertas.motor import evaluar_negocio
    from apps.inventario.services import crear_conteo
    from apps.recomendaciones.models import RecomendacionCompra
    from apps.recomendaciones.services import generar_recomendaciones

    *_, almuerzo = cocina
    evaluar_negocio(negocio)
    generar_recomendaciones(negocio)
    conteo = crear_conteo(negocio, admin)
    assert not Alerta.objects.filter(producto=almuerzo).exists()
    assert not RecomendacionCompra.objects.filter(producto=almuerzo).exists()
    assert not conteo.detalles.filter(producto=almuerzo).exists()


def test_receta_desde_la_ficha(client, negocio, admin, cocina):
    arroz, pollo, almuerzo = cocina
    client.force_login(admin)
    html = client.get(f"/productos/{almuerzo.pk}/").content.decode()
    assert "Se puede preparar" in html and "Arroz" in html
    item = RecetaItem.objects.get(producto=almuerzo, insumo=arroz)
    client.post(f"/productos/{almuerzo.pk}/receta/{item.pk}/quitar/")
    almuerzo.refresh_from_db()
    assert almuerzo.precio_compra == Decimal("3300.00")
    ajeno = Producto.objects.create(negocio=Negocio.objects.create(nombre="Otro"), sku="Y", nombre="Ajeno")
    assert client.post(f"/productos/{almuerzo.pk}/receta/", {"insumo": ajeno.pk, "cantidad": 1}).status_code == 404
    client.post(f"/productos/{almuerzo.pk}/receta/", {"insumo": arroz.pk, "cantidad": "0.2"})
    assert RecetaItem.objects.get(producto=almuerzo, insumo=arroz).cantidad == Decimal("0.2")
    assert "Se usa en" in client.get(f"/productos/{arroz.pk}/").content.decode()


def test_producir_desde_la_ficha(client, negocio, admin):
    harina = Producto.objects.create(negocio=negocio, sku="HAR", nombre="Harina", tipo=TipoProducto.INSUMO)
    pan = Producto.objects.create(negocio=negocio, sku="PAN", nombre="Pan", precio_venta=800)
    registrar_movimiento(producto=harina, tipo=TipoMovimiento.ENTRADA_INICIAL, cantidad=5)
    guardar_item_receta(pan, harina, "0.05")
    client.force_login(admin)
    assert "Registrar producción" in client.get(f"/productos/{pan.pk}/").content.decode()
    client.post(f"/productos/{pan.pk}/producir/", {"cantidad": "20"})
    pan.refresh_from_db()
    assert pan.stock_actual == 20


def test_no_se_convierte_en_preparado_con_stock(client, negocio, admin, producto):
    registrar_movimiento(producto=producto, tipo=TipoMovimiento.ENTRADA_INICIAL, cantidad=3)
    client.force_login(admin)
    r = client.post(f"/productos/{producto.pk}/editar/", {
        "tipo": "PREPARADO", "nombre": producto.nombre, "sku": producto.sku, "precio_compra": 1, "precio_venta": 2,
        "stock_minimo": 0, "activo": "on"})
    assert "stock en cero" in r.content.decode()
    producto.refresh_from_db()
    assert producto.tipo == TipoProducto.PRODUCTO


def test_insumo_en_unidades_enteras_no_admite_fracciones_en_la_receta(negocio, cocina):
    """Hallazgo del piloto simulado: si se aceptaba, cada venta del preparado fallaba después."""
    from apps.catalogo.models import UnidadMedida

    *_, almuerzo = cocina
    und = UnidadMedida.objects.get(abreviatura="und")
    limon = Producto.objects.create(negocio=negocio, sku="LIM", nombre="Limón", tipo=TipoProducto.INSUMO, unidad=und)
    with pytest.raises(ErrorInventario, match="unidades enteras"):
        guardar_item_receta(almuerzo, limon, "0.5")
    guardar_item_receta(almuerzo, limon, 1)
