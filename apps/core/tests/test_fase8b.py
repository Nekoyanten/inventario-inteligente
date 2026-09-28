"""Fase 8b: perecederos, ciclo de compra, ropa por familia, precisión WAPE, recepción rápida y conteo cíclico."""

import io
from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from PIL import Image

from apps.analitica import algoritmos as alg
from apps.analitica.models import DemandaDiaria, RegistroPronostico
from apps.analitica.services import (
    ciclo_compra,
    curva_variantes,
    horizonte_compra,
    precision_negocio,
    registrar_y_evaluar_pronosticos,
)
from apps.catalogo.models import Producto
from apps.compras.models import OrdenCompra
from apps.compras.services import cerrar_recepcion, crear_orden, enviar_orden, recibir_orden, recibir_todo
from apps.core.models import Negocio
from apps.inventario.models import ConteoFisico, Lote, TipoMovimiento
from apps.inventario.services import crear_conteo_ciclico, productos_para_conteo_ciclico, registrar_movimiento
from apps.proveedores.models import Proveedor
from apps.recomendaciones.models import RecomendacionCompra
from apps.recomendaciones.services import generar_recomendaciones, recomendar_producto

pytestmark = pytest.mark.django_db
HOY = timezone.localdate()


def _ventas(producto, por_dia, dias, hasta=HOY):
    for i in range(dias):
        DemandaDiaria.objects.create(producto=producto, fecha=hasta - timedelta(days=i), cantidad=por_dia)


# ---------------------------------------------------------------- P1: vida útil
def test_tope_por_vida_util():
    assert alg.tope_por_vida_util(demanda_diaria=2, vida_util=4, tiempo_entrega=3, stock=0) == 8
    # lo que quede al llegar el pedido se vende primero y le quita vida al pedido nuevo
    assert alg.tope_por_vida_util(demanda_diaria=2, vida_util=4, tiempo_entrega=1, stock=6) == 4
    assert alg.tope_por_vida_util(demanda_diaria=2, vida_util=None, tiempo_entrega=1, stock=0) is None


def test_pedido_de_perecedero_no_supera_lo_que_se_alcanza_a_vender(negocio, producto, proveedor):
    proveedor.tiempo_entrega_dias = 7  # proveedor lento
    proveedor.save()
    producto.vida_util_dias = 4
    producto.stock_minimo = 5
    producto.save()
    _ventas(producto, 5, 30)
    rec = recomendar_producto(producto, HOY)
    assert rec.cantidad_sugerida <= 20  # 5/día × 4 días
    assert "dura 4 días" in rec.explicacion
    assert "tarda tanto como lo que dura" in rec.explicacion


def test_compra_sin_fecha_de_vencimiento_la_calcula_con_la_vida_util(negocio, admin, producto):
    producto.vida_util_dias = 5
    producto.save()
    registrar_movimiento(producto=producto, tipo=TipoMovimiento.ENTRADA_COMPRA, cantidad=10, usuario=admin)
    assert Lote.objects.get(producto=producto).fecha_vencimiento == HOY + timedelta(days=5)


# ---------------------------------------------------------------- P11: horizonte = ciclo real de compra
def _orden_enviada(negocio, proveedor, admin, producto, dias_atras):
    orden = crear_orden(negocio=negocio, proveedor=proveedor, usuario=admin,
                        lineas=[{"producto": producto, "cantidad": 1, "costo": 1}])
    enviar_orden(orden, admin, fecha=timezone.now() - timedelta(days=dias_atras))
    return orden


def test_ciclo_de_compra_y_horizonte(negocio, admin, proveedor, producto):
    assert ciclo_compra(proveedor) is None
    for d in (42, 28, 14, 0):
        _orden_enviada(negocio, proveedor, admin, producto, d)
    assert ciclo_compra(proveedor) == 14
    assert horizonte_compra(producto) == (14, "ciclo")
    negocio.config.horizonte_compra_dias = 20  # si compra más seguido que el horizonte, se conserva el horizonte
    negocio.config.save()
    producto.refresh_from_db()
    assert horizonte_compra(producto) == (20, "configuracion")
    negocio.config.horizonte_compra_dias = 7
    negocio.config.horizonte_automatico = False
    negocio.config.save()
    producto.refresh_from_db()
    assert horizonte_compra(producto) == (7, "configuracion")


def test_recomendacion_explica_el_ciclo(negocio, admin, proveedor, producto):
    for d in (42, 28, 14):
        _orden_enviada(negocio, proveedor, admin, producto, d)
    OrdenCompra.objects.update(estado=OrdenCompra.Estado.CANCELADA)  # no cuentan
    assert ciclo_compra(proveedor) is None
    for d in (30, 20, 10):
        o = _orden_enviada(negocio, proveedor, admin, producto, d)
        recibir_orden(o, admin, {o.detalles.first().pk: 1})
    _ventas(producto, 3, 30)
    rec = recomendar_producto(producto, HOY)
    assert "Haces pedidos cada ~10 días" in rec.explicacion


# ---------------------------------------------------------------- P8: ropa por familia y curva de tallas
@pytest.fixture
def ropa(db):
    negocio = Negocio.objects.create(nombre="Boutique", giro="ROPA")
    prov = Proveedor.objects.create(negocio=negocio, nombre="Confeccionista", tiempo_entrega_dias=5)
    padre = Producto.objects.create(negocio=negocio, sku="JEAN", nombre="Jean", es_agrupador=True)
    tallas = {t: Producto.objects.create(negocio=negocio, sku=f"JEAN-{t}", nombre=f"Jean {t}", padre=padre,
                                         proveedor_principal=prov, precio_compra=30000, precio_venta=60000)
              for t in ("S", "M", "L")}
    return negocio, padre, tallas


def test_curva_de_tallas(ropa):
    _, padre, tallas = ropa
    _ventas(tallas["M"], 1, 20)   # M: 20 ventas
    _ventas(tallas["S"], 1, 5)    # S: 5
    curva = curva_variantes(padre)
    assert curva[tallas["M"].pk] > curva[tallas["S"].pk] > curva[tallas["L"].pk] > 0
    assert abs(sum(curva.values()) - 1) < 1e-9


def test_recomendacion_por_familia_reparte_segun_la_curva(ropa):
    negocio, padre, tallas = ropa
    _ventas(tallas["M"], 2, 30)
    _ventas(tallas["S"], 1, 30)
    recs = {r.producto_id: r for r in generar_recomendaciones(negocio, HOY)}
    assert recs[tallas["M"].pk].cantidad_sugerida > recs[tallas["S"].pk].cantidad_sugerida
    assert "curva de tallas" in recs[tallas["M"].pk].explicacion
    assert not RecomendacionCompra.objects.filter(producto=padre).exists()


def test_pronostico_de_ropa_se_registra_por_familia(ropa):
    negocio, padre, tallas = ropa
    _ventas(tallas["M"], 1, 20, hasta=HOY - timedelta(days=40))
    registrar_y_evaluar_pronosticos(negocio, hoy=HOY - timedelta(days=40))
    assert RegistroPronostico.objects.filter(producto=padre).exists()
    assert not RegistroPronostico.objects.filter(producto__padre=padre).exists()
    _ventas(tallas["M"], 1, 29, hasta=HOY - timedelta(days=11))
    registrar_y_evaluar_pronosticos(negocio, hoy=HOY)
    reg = RegistroPronostico.objects.get(producto=padre, desde=HOY - timedelta(days=40))
    assert reg.real == 30


# ---------------------------------------------------------------- P12: precisión con WAPE y días agotado
def test_precision_wape_corrige_dias_agotado(producto):
    desde = HOY - timedelta(days=40)
    RegistroPronostico.objects.create(producto=producto, desde=desde, hasta=desde + timedelta(days=29),
                                      pronosticado=30, real=15, dias_agotado=15)  # medio mes agotado → real ≈ 30
    otro = Producto.objects.create(negocio=producto.negocio, sku="Z", nombre="Casi siempre agotado")
    RegistroPronostico.objects.create(producto=otro, desde=desde, hasta=desde + timedelta(days=29),
                                      pronosticado=30, real=1, dias_agotado=25)
    r = precision_negocio(producto.negocio)
    assert r["wape"] == 0 and r["acierto"] == 100
    assert r["periodos"] == 1 and r["excluidos"] == 1


def test_wape_no_lo_distorsionan_productos_de_poca_venta(negocio):
    desde = HOY - timedelta(days=40)
    grande = Producto.objects.create(negocio=negocio, sku="G", nombre="Grande")
    chico = Producto.objects.create(negocio=negocio, sku="C", nombre="Chico")
    RegistroPronostico.objects.create(producto=grande, desde=desde, hasta=desde + timedelta(days=29), pronosticado=110,
                                      real=100)
    RegistroPronostico.objects.create(producto=chico, desde=desde, hasta=desde + timedelta(days=29), pronosticado=3,
                                      real=1)  # MAPE 200 %
    assert precision_negocio(negocio)["wape"] == pytest.approx(11.9, abs=0.1)


def test_reporte_de_precision_muestra_el_acierto_del_negocio(client, admin, producto):
    desde = HOY - timedelta(days=40)
    RegistroPronostico.objects.create(producto=producto, desde=desde, hasta=desde + timedelta(days=29),
                                      pronosticado=90, real=100)
    client.force_login(admin)
    html = client.get("/reportes/precision-pronosticos/").content.decode()
    assert "acierta ~90 %" in html


# ---------------------------------------------------------------- P3: recepción rápida
def _foto():
    buf = io.BytesIO()
    Image.new("RGB", (40, 30), "white").save(buf, "JPEG")
    return SimpleUploadedFile("factura.jpg", buf.getvalue(), content_type="image/jpeg")


def test_llego_todo_en_un_toque_con_foto(client, negocio, admin, proveedor, producto, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    orden = crear_orden(negocio=negocio, proveedor=proveedor, usuario=admin,
                        lineas=[{"producto": producto, "cantidad": 12, "costo": 8000}])
    enviar_orden(orden, admin)
    client.force_login(admin)
    client.post(f"/compras/{orden.pk}/recibir_todo/", {"numero_factura": "F-1", "factura_imagen": _foto()})
    orden.refresh_from_db()
    producto.refresh_from_db()
    assert orden.estado == OrdenCompra.Estado.RECIBIDA and orden.numero_factura == "F-1"
    assert producto.stock_actual == 12
    assert orden.factura_imagen.name.endswith(".webp")


def test_llego_todo_desde_la_lista_de_ordenes(client, negocio, admin, proveedor, producto):
    orden = crear_orden(negocio=negocio, proveedor=proveedor, usuario=admin,
                        lineas=[{"producto": producto, "cantidad": 3, "costo": 1}])
    enviar_orden(orden, admin)
    client.force_login(admin)
    html = client.get("/compras/").content.decode()
    assert "Llegó todo" in html
    r = client.post(f"/compras/{orden.pk}/recibir_todo/", {"volver": "/compras/"})
    assert r.url == "/compras/"
    orden.refresh_from_db()
    assert orden.estado == OrdenCompra.Estado.RECIBIDA


def test_cerrar_recepcion_parcial(negocio, admin, proveedor, producto):
    from apps.analitica.services import unidades_en_transito

    orden = crear_orden(negocio=negocio, proveedor=proveedor, usuario=admin,
                        lineas=[{"producto": producto, "cantidad": 10, "costo": 1}])
    enviar_orden(orden, admin)
    recibir_orden(orden, admin, {orden.detalles.first().pk: 6})
    assert unidades_en_transito(producto) == 4
    cerrar_recepcion(orden, admin)
    orden.refresh_from_db()
    assert orden.estado == OrdenCompra.Estado.RECIBIDA and "Cerrada sin recibir" in orden.observaciones
    assert unidades_en_transito(producto) == 0
    assert orden.dias_entrega == 0


def test_recibir_todo_sin_pendientes_falla(negocio, admin, proveedor, producto):
    from apps.inventario.services import ErrorInventario

    orden = crear_orden(negocio=negocio, proveedor=proveedor, usuario=admin,
                        lineas=[{"producto": producto, "cantidad": 1, "costo": 1}])
    enviar_orden(orden, admin)
    recibir_todo(orden, admin)
    with pytest.raises(ErrorInventario):
        recibir_todo(orden, admin)


# ---------------------------------------------------------------- P4: conteo cíclico
def test_conteo_ciclico_prioriza_lo_que_mas_se_vende_y_lo_sospechoso(negocio, admin):
    from apps.alertas.models import Alerta
    from apps.ventas.services import registrar_venta

    productos = [Producto.objects.create(negocio=negocio, sku=f"C{i}", nombre=f"Prod {i}", precio_venta=1000 + i)
                 for i in range(25)]
    estrella, sospechoso = productos[0], productos[1]
    registrar_movimiento(producto=estrella, tipo=TipoMovimiento.ENTRADA_INICIAL, cantidad=100)
    for _ in range(5):
        registrar_venta(negocio=negocio, vendedor=admin, lineas=[{"producto": estrella, "cantidad": 3}])
    Alerta.objects.create(negocio=negocio, producto=sospechoso, tipo=Alerta.Tipo.VENTA_SIN_STOCK, mensaje="x")
    elegidos = productos_para_conteo_ciclico(negocio)
    assert len(elegidos) == 10
    assert elegidos[0] == sospechoso and estrella in elegidos[:3]


def test_conteo_ciclico_rota_los_productos(negocio, admin):
    from apps.inventario.services import aprobar_conteo, enviar_conteo

    for i in range(20):
        Producto.objects.create(negocio=negocio, sku=f"R{i}", nombre=f"R{i}")
    primero = crear_conteo_ciclico(negocio, admin)
    enviar_conteo(primero, admin)
    aprobar_conteo(primero, admin)
    contados = set(primero.detalles.values_list("producto_id", flat=True))
    segundo = set(p.pk for p in productos_para_conteo_ciclico(negocio))
    assert not contados & segundo


def test_boton_conteo_del_dia(client, negocio, admin, producto):
    client.force_login(admin)
    r = client.post("/inventario/conteos/", {"tipo": "ciclico"})
    conteo = ConteoFisico.objects.get()
    assert r.url == f"/inventario/conteos/{conteo.pk}/"
    assert "Conteo del día" in conteo.observaciones


def test_vida_util_en_importacion(negocio, admin):
    from apps.reportes.importacion import importar_filas, validar

    limpias, errores = validar(negocio, [{"sku": "POLLO", "nombre": "Pollo", "vida_util_dias": "4"},
                                               {"sku": "X", "nombre": "X", "vida_util_dias": "-1"}])
    assert errores and "vida útil" in errores[0]
    importar_filas(negocio, admin, limpias[:1])
    assert Producto.objects.get(sku="POLLO").vida_util_dias == 4



def test_curva_rota_sugiere_reponer_la_talla_agotada_que_se_vende(ropa):
    negocio, padre, tallas = ropa
    registrar_movimiento(producto=tallas["S"], tipo=TipoMovimiento.ENTRADA_INICIAL, cantidad=50)
    _ventas(tallas["M"], 1, 10, hasta=HOY - timedelta(days=20))  # la M se vendía y hace 20 días está en 0
    _ventas(tallas["S"], 1, 10, hasta=HOY - timedelta(days=20))
    recs = {r.producto_id: r for r in generar_recomendaciones(negocio, HOY)}
    assert "curva de tallas" in recs[tallas["M"].pk].explicacion
    assert tallas["L"].pk not in recs  # la L nunca se ha vendido


def test_curva_rota_repone_la_talla_aunque_su_demanda_propia_no_alcance(ropa):
    from apps.recomendaciones.services import recomendar_familia

    negocio, padre, tallas = ropa
    _ventas(tallas["M"], 1, 5, hasta=HOY - timedelta(days=80))  # vendió hace tiempo; su demanda reciente es ~0
    _ventas(tallas["S"], 1, 4, hasta=HOY - timedelta(days=80))
    nuevas = recomendar_familia(padre, HOY, {}, {})
    assert {r.producto_id for r in nuevas} == {tallas["M"].pk, tallas["S"].pk}
    assert all("curva de tallas queda rota" in r.explicacion for r in nuevas)


def test_con_ciclo_conocido_se_pide_antes_de_la_proxima_compra(negocio, admin, proveedor, producto):
    for d in (42, 28, 14, 0):
        _orden_enviada(negocio, proveedor, admin, producto, d)
    OrdenCompra.objects.update(estado=OrdenCompra.Estado.CANCELADA)
    for d in (42, 28, 14):
        o = _orden_enviada(negocio, proveedor, admin, producto, d)
        recibir_orden(o, admin, {o.detalles.first().pk: 1})
    producto.stock_minimo = 0
    producto.save()
    _ventas(producto, 2, 30)
    registrar_movimiento(producto=producto, tipo=TipoMovimiento.ENTRADA_INICIAL, cantidad=20)
    # 20 u. alcanzan 10 días: más que el tiempo de entrega (4) pero menos que hasta la próxima compra (14 + 4)
    assert recomendar_producto(producto, HOY) is not None


def test_paginas_nuevas_de_la_fase8(client, admin, negocio, proveedor, producto):
    Proveedor.objects.create(negocio=negocio, nombre="Otro")
    padre = Producto.objects.create(negocio=negocio, sku="PADRE", nombre="Camisa", es_agrupador=True)
    Producto.objects.create(negocio=negocio, sku="PADRE-S", nombre="Camisa S", padre=padre)
    o = crear_orden(negocio=negocio, proveedor=proveedor, usuario=admin,
                    lineas=[{"producto": producto, "cantidad": 4, "costo": 1}])
    enviar_orden(o, admin)
    recibir_orden(o, admin, {o.detalles.first().pk: 2})
    client.force_login(admin)
    for url in ["/negocio/cerrar-cuenta/", f"/proveedores/{proveedor.pk}/", f"/compras/{o.pk}/", "/compras/",
                "/compras/factura/", "/inventario/conteos/", f"/productos/{padre.pk}/",
                f"/productos/{producto.pk}/editar/", "/usuarios/nuevo/", "/negocio/configuracion/",
                "/alertas/?vista=todas", "/ventas/vender/", "/ayuda/", "/privacidad/",
                "/reportes/precision-pronosticos/", "/compras/que-comprar/"]:
        r = client.get(url)
        assert r.status_code == 200, url
        html = r.content.decode()
        assert "{%" not in html and "{{" not in html, url
    html = client.get(f"/compras/{o.pk}/").content.decode()
    assert "Llegó todo" in html and "cerrar con lo recibido" in html
    assert "Cambiar de proveedor" in client.get(f"/proveedores/{proveedor.pk}/").content.decode()
    assert "Vida útil" in client.get(f"/productos/{producto.pk}/editar/").content.decode()
