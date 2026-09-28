"""Fase 8a: cambios pequeños que atacan las causas de abandono vistas en el piloto simulado."""

import json

import pytest
from django.core.cache import cache

from apps.alertas.models import Alerta
from apps.catalogo.models import Categoria, Producto
from apps.compras.models import OrdenCompra
from apps.compras.services import crear_orden, enviar_orden
from apps.core.models import Negocio
from apps.inventario.models import Movimiento, TipoMovimiento
from apps.inventario.services import ErrorInventario, registrar_movimiento
from apps.proveedores.models import ProductoProveedor, Proveedor
from apps.proveedores.services import desempeno, reemplazar_proveedor
from apps.usuarios.models import Rol, Usuario
from apps.ventas.models import Venta
from apps.ventas.services import cantidades_inusuales, registrar_venta

pytestmark = pytest.mark.django_db


def _stock(producto, cantidad, usuario=None):
    registrar_movimiento(producto=producto, tipo=TipoMovimiento.ENTRADA_INICIAL, cantidad=cantidad, usuario=usuario)
    producto.refresh_from_db()


# ---------------------------------------------------------------- P2: vender aunque el sistema diga 0
def test_venta_sin_stock_se_registra_con_ajuste_y_alerta(negocio, admin, producto):
    _stock(producto, 1)
    venta = registrar_venta(negocio=negocio, vendedor=admin, lineas=[{"producto": producto, "cantidad": 3}])
    producto.refresh_from_db()
    assert venta.total == 36000
    assert producto.stock_actual == 0
    ajuste = Movimiento.objects.get(producto=producto, referencia_tipo="venta_sin_stock")
    assert ajuste.tipo == TipoMovimiento.ENTRADA_AJUSTE and ajuste.cantidad == 2
    alerta = Alerta.objects.get(producto=producto, tipo=Alerta.Tipo.VENTA_SIN_STOCK)
    assert "2" in alerta.mensaje

    # una segunda venta acumula en la misma alerta en vez de crear otra
    registrar_venta(negocio=negocio, vendedor=admin, lineas=[{"producto": producto, "cantidad": 1}])
    alerta.refresh_from_db()
    assert Alerta.objects.filter(producto=producto, tipo=Alerta.Tipo.VENTA_SIN_STOCK).count() == 1
    assert alerta.datos["cantidad"] == 3 and len(alerta.datos["ventas"]) == 2


def test_la_alerta_de_venta_sin_stock_no_se_autoresuelve(negocio, admin, producto):
    from apps.alertas.motor import evaluar_producto

    registrar_venta(negocio=negocio, vendedor=admin, lineas=[{"producto": producto, "cantidad": 1}])
    _stock(producto, 50)
    evaluar_producto(producto.pk)
    assert Alerta.objects.get(producto=producto, tipo=Alerta.Tipo.VENTA_SIN_STOCK).estado == Alerta.Estado.ABIERTA


def test_negocio_que_no_permite_venta_sin_stock_la_bloquea(negocio, admin, producto):
    negocio.config.permite_venta_sin_stock = False
    negocio.config.save()
    with pytest.raises(ErrorInventario):
        registrar_venta(negocio=negocio, vendedor=admin, lineas=[{"producto": producto, "cantidad": 1}])
    assert not Venta.objects.exists()


def test_farmacia_no_vende_sin_stock_por_defecto(db):
    farmacia = Negocio.objects.create(nombre="Droguería", giro="FARMACIA")
    assert farmacia.config.permite_venta_sin_stock is False


# ---------------------------------------------------------------- P7: confirmar cantidades inusuales
def test_cantidad_inusual_pide_confirmacion_en_el_punto_de_venta(client, negocio, admin, producto):
    _stock(producto, 500)
    for _ in range(4):
        registrar_venta(negocio=negocio, vendedor=admin, lineas=[{"producto": producto, "cantidad": 2}])
    client.force_login(admin)
    cuerpo = {"lineas": [{"producto": producto.pk, "cantidad": 20}]}
    r = client.post("/ventas/registrar/", json.dumps(cuerpo), content_type="application/json")
    assert r.status_code == 428
    assert r.json()["confirmar"][0]["habitual"] == 10
    assert Venta.objects.count() == 4

    r = client.post("/ventas/registrar/", json.dumps({**cuerpo, "confirmado": True}), content_type="application/json")
    assert r.status_code == 200
    assert Venta.objects.count() == 5


def test_cantidad_normal_no_pide_confirmacion(negocio, admin, producto):
    _stock(producto, 100)
    for _ in range(3):
        registrar_venta(negocio=negocio, vendedor=admin, lineas=[{"producto": producto, "cantidad": 2}])
    assert cantidades_inusuales([{"producto": producto, "cantidad": 3}]) == []
    # producto sin historia: umbral generoso (10)
    otro = Producto.objects.create(negocio=negocio, sku="X", nombre="Nuevo", precio_venta=100)
    assert cantidades_inusuales([{"producto": otro, "cantidad": 10}]) == []
    assert cantidades_inusuales([{"producto": otro, "cantidad": 11}])


# ---------------------------------------------------------------- P9: consumo interno
def test_consumo_interno_descuenta_y_cuenta_como_demanda(negocio, admin, producto):
    from apps.analitica.models import DemandaDiaria

    _stock(producto, 10)
    registrar_movimiento(producto=producto, tipo=TipoMovimiento.SALIDA_CONSUMO_INTERNO, cantidad=3, usuario=admin)
    producto.refresh_from_db()
    assert producto.stock_actual == 7
    assert DemandaDiaria.objects.get(producto=producto).cantidad == 3


def test_consumo_interno_aparece_en_el_formulario(client, admin, negocio):
    client.force_login(admin)
    assert "Consumo interno" in client.get("/inventario/").content.decode()


# ---------------------------------------------------------------- P5: bandeja «Hoy» y silenciar
def _alerta(negocio, producto, tipo, severidad):
    return Alerta.objects.create(negocio=negocio, producto=producto, tipo=tipo, severidad=severidad,
                                 mensaje=f"{tipo} {producto.nombre}",
                                 datos={"valor_inmovilizado": 1000})


def test_bandeja_hoy_muestra_diez_y_resume_baja_rotacion(client, negocio, admin):
    cat = Categoria.objects.filter(negocio=negocio).first()
    for i in range(15):
        p = Producto.objects.create(negocio=negocio, sku=f"A{i}", nombre=f"Urgente {i}", categoria=cat)
        _alerta(negocio, p, Alerta.Tipo.AGOTADO, Alerta.Severidad.ACTUAR)
    for i in range(30):
        p = Producto.objects.create(negocio=negocio, sku=f"B{i}", nombre=f"Quieto {i}", categoria=cat)
        _alerta(negocio, p, Alerta.Tipo.BAJA_ROTACION, Alerta.Severidad.REVISAR)
    client.force_login(admin)
    html = client.get("/alertas/").content.decode()
    assert html.count('class="alerta s3"') == 10
    assert "Ver 5 alertas más" in html
    assert "30 productos" in html and "Quieto 0" not in html
    # «Todas» sigue mostrando todo
    assert "Quieto 0" in client.get("/alertas/?estado=abiertas&vista=todas").content.decode()


def test_silenciar_baja_rotacion_en_una_categoria(client, negocio, admin):
    from apps.alertas.silencio import esta_silenciada

    cat = Categoria.objects.filter(negocio=negocio).first()
    p = Producto.objects.create(negocio=negocio, sku="Q", nombre="Tornillo", categoria=cat)
    a = _alerta(negocio, p, Alerta.Tipo.BAJA_ROTACION, Alerta.Severidad.REVISAR)
    client.force_login(admin)
    client.post("/alertas/silenciar/", {"tipo": "BAJA_ROTACION", "categoria": cat.pk})
    a.refresh_from_db()
    negocio.config.refresh_from_db()
    assert a.estado == Alerta.Estado.DESCARTADA
    assert esta_silenciada(negocio.config, "BAJA_ROTACION", cat.pk)
    assert not esta_silenciada(negocio.config, "BAJA_ROTACION", None)
    assert not esta_silenciada(negocio.config, "AGOTADO", cat.pk)
    client.post("/alertas/reactivar/", {"tipo": "BAJA_ROTACION", "categoria": cat.pk})
    negocio.config.refresh_from_db()
    assert negocio.config.alertas_silenciadas == []


def test_no_se_pueden_silenciar_agotados(client, negocio, admin):
    client.force_login(admin)
    client.post("/alertas/silenciar/", {"tipo": "AGOTADO"})
    negocio.config.refresh_from_db()
    assert negocio.config.alertas_silenciadas == []


def test_motor_respeta_alertas_silenciadas(negocio, producto):
    from apps.alertas.motor import evaluar_producto
    from apps.alertas.silencio import silenciar

    silenciar(negocio, None, "STOCK_BAJO", None)
    _stock(producto, 6)  # mínimo 8 → stock bajo
    tipos = {a.tipo for a in evaluar_producto(producto.pk)}
    assert "STOCK_BAJO" not in tipos


def test_producto_nuevo_no_genera_baja_rotacion(negocio, producto):
    from apps.alertas.motor import evaluar_producto

    _stock(producto, 50)
    assert "BAJA_ROTACION" not in {a.tipo for a in evaluar_producto(producto.pk)}


# ---------------------------------------------------------------- P6: cambio masivo de proveedor
def test_reemplazar_proveedor_pasa_productos_ordenes_y_precios(negocio, admin, proveedor):
    cat = Categoria.objects.filter(negocio=negocio).first()
    otra = Categoria.objects.filter(negocio=negocio).exclude(pk=cat.pk).first()
    nuevo = Proveedor.objects.create(negocio=negocio, nombre="Confiable", tiempo_entrega_dias=2)
    productos = [Producto.objects.create(negocio=negocio, sku=f"P{i}", nombre=f"P{i}", categoria=cat,
                                         proveedor_principal=proveedor, precio_compra=100) for i in range(5)]
    fuera = Producto.objects.create(negocio=negocio, sku="F", nombre="Otra categoría", categoria=otra,
                                    proveedor_principal=proveedor)
    ProductoProveedor.objects.create(proveedor=proveedor, producto=productos[0], precio_compra=90, multiplo_empaque=6)
    linea = [{"producto": productos[0], "cantidad": 2, "costo": 90}]
    borrador = crear_orden(negocio=negocio, proveedor=proveedor, usuario=admin, lineas=linea)
    enviada = crear_orden(negocio=negocio, proveedor=proveedor, usuario=admin, lineas=linea)
    enviar_orden(enviada, admin)

    r = reemplazar_proveedor(origen=proveedor, destino=nuevo, usuario=admin, categoria=cat, ordenes="esperar",
                             desactivar=True)
    assert r["productos"] == 5 and r["borradores_movidos"] == 1 and r["ordenes_en_camino"] == 1
    assert Producto.objects.filter(proveedor_principal=nuevo).count() == 5
    fuera.refresh_from_db()
    assert fuera.proveedor_principal == proveedor
    proveedor.refresh_from_db()
    assert proveedor.activo  # todavía surte la otra categoría
    pp = ProductoProveedor.objects.get(proveedor=nuevo, producto=productos[0])
    assert pp.precio_compra == 90 and pp.multiplo_empaque == 6
    borrador.refresh_from_db()
    enviada.refresh_from_db()
    assert borrador.proveedor == nuevo and enviada.proveedor == proveedor


def test_reemplazar_todo_y_cancelar_ordenes_desactiva_el_viejo(client, negocio, admin, proveedor, producto):
    nuevo = Proveedor.objects.create(negocio=negocio, nombre="Confiable")
    orden = crear_orden(negocio=negocio, proveedor=proveedor, usuario=admin,
                        lineas=[{"producto": producto, "cantidad": 2, "costo": 1}])
    enviar_orden(orden, admin)
    client.force_login(admin)
    r = client.post(f"/proveedores/{proveedor.pk}/reemplazar/",
                    {"destino": nuevo.pk, "ordenes": "cancelar", "desactivar": "1"})
    assert r.status_code == 302
    proveedor.refresh_from_db()
    orden.refresh_from_db()
    assert not proveedor.activo
    assert orden.estado == OrdenCompra.Estado.CANCELADA


def test_no_se_reemplaza_por_proveedor_de_otro_negocio(client, negocio, admin, proveedor, producto):
    ajeno = Proveedor.objects.create(negocio=Negocio.objects.create(nombre="Otro"), nombre="Ajeno")
    client.force_login(admin)
    r = client.post(f"/proveedores/{proveedor.pk}/reemplazar/", {"destino": ajeno.pk})
    assert r.status_code == 404
    producto.refresh_from_db()
    assert producto.proveedor_principal == proveedor


def test_desempeno_avisa_cuando_no_hay_entregas(proveedor):
    d = desempeno(proveedor)
    assert d["entregas"] == 0 and d["tiempo_promedio"] is None


def test_recomendacion_aclara_que_el_tiempo_es_el_prometido(negocio, producto):
    from apps.recomendaciones.services import recomendar_producto

    rec = recomendar_producto(producto)
    assert "prometió" in rec.explicacion


# ---------------------------------------------------------------- P10: PIN por empleado
def test_cambio_de_usuario_con_pin(client, negocio, admin):
    cache.clear()
    vendedor = Usuario.objects.create_user("ana", password="x", negocio=negocio, rol=Rol.VENDEDOR, first_name="Ana")
    vendedor.fijar_pin("1234")
    vendedor.save()
    client.force_login(admin)
    assert "Ana" in client.get("/usuarios/cambiar/").content.decode()
    r = client.post("/usuarios/cambiar/", {"usuario": vendedor.pk, "pin": "0000"})
    assert "PIN incorrecto" in r.content.decode()
    r = client.post("/usuarios/cambiar/", {"usuario": vendedor.pk, "pin": "1234"})
    assert r.status_code == 302
    assert int(client.session["_auth_user_id"]) == vendedor.pk


def test_pin_bloquea_tras_varios_intentos_y_no_sirve_para_admins(client, negocio, admin):
    cache.clear()
    admin.fijar_pin("1111")
    admin.save()
    vendedor = Usuario.objects.create_user("beto", password="x", negocio=negocio, rol=Rol.VENDEDOR)
    vendedor.fijar_pin("1234")
    vendedor.save()
    client.force_login(vendedor)
    r = client.post("/usuarios/cambiar/", {"usuario": admin.pk, "pin": "1111"})
    assert int(client.session["_auth_user_id"]) == vendedor.pk  # al administrador no se entra con PIN
    for _ in range(5):
        client.post("/usuarios/cambiar/", {"usuario": vendedor.pk, "pin": "9999"})
    r = client.post("/usuarios/cambiar/", {"usuario": vendedor.pk, "pin": "1234"})
    assert "Demasiados intentos" in r.content.decode()


def test_no_se_cambia_a_usuario_de_otro_negocio(client, negocio, admin):
    cache.clear()
    otro = Usuario.objects.create_user("zoe", password="x", negocio=Negocio.objects.create(nombre="Otro"),
                                       rol=Rol.VENDEDOR)
    otro.fijar_pin("1234")
    otro.save()
    client.force_login(admin)
    client.post("/usuarios/cambiar/", {"usuario": otro.pk, "pin": "1234"})
    assert int(client.session["_auth_user_id"]) == admin.pk


def test_admin_asigna_pin_en_el_formulario(client, negocio, admin):
    vendedor = Usuario.objects.create_user("caro", password="x", negocio=negocio, rol=Rol.VENDEDOR)
    client.force_login(admin)
    client.post(f"/usuarios/{vendedor.pk}/", {"first_name": "Caro", "rol": "VENDEDOR", "is_active": "on",
                                              "pin_nuevo": "4321"})
    vendedor.refresh_from_db()
    assert vendedor.verificar_pin("4321") and not vendedor.pin == "4321"
    r = client.post(f"/usuarios/{vendedor.pk}/", {"first_name": "Caro", "rol": "VENDEDOR", "is_active": "on",
                                                  "pin_nuevo": "12a"})
    assert "de 4 a 6 números" in r.content.decode()


# ---------------------------------------------------------------- P13: cerrar la cuenta
def test_cerrar_cuenta_borra_todo_el_negocio(client, negocio, admin, producto, proveedor):
    otro = Negocio.objects.create(nombre="Vecino")
    Producto.objects.create(negocio=otro, sku="V", nombre="Del vecino")
    _stock(producto, 5, admin)
    registrar_venta(negocio=negocio, vendedor=admin, lineas=[{"producto": producto, "cantidad": 1}])
    orden = crear_orden(negocio=negocio, proveedor=proveedor, usuario=admin,
                        lineas=[{"producto": producto, "cantidad": 2, "costo": 1}])
    enviar_orden(orden, admin)
    client.force_login(admin)
    r = client.post("/negocio/cerrar-cuenta/", {"confirmacion": "otro nombre", "password": "x"})
    assert Negocio.objects.filter(pk=negocio.pk).exists()
    r = client.post("/negocio/cerrar-cuenta/", {"confirmacion": "tienda test", "password": "x"})
    assert r.status_code == 302
    assert not Negocio.objects.filter(pk=negocio.pk).exists()
    assert not Usuario.objects.filter(pk=admin.pk).exists()
    assert not Movimiento.objects.filter(negocio_id=negocio.pk).exists()
    assert Producto.objects.filter(negocio=otro).count() == 1  # los demás negocios no se tocan


def test_vendedor_no_puede_cerrar_la_cuenta(client, negocio):
    vendedor = Usuario.objects.create_user("v", password="x", negocio=negocio, rol=Rol.VENDEDOR)
    client.force_login(vendedor)
    assert client.post("/negocio/cerrar-cuenta/", {"confirmacion": "Tienda Test", "password": "x"}).status_code == 403
    assert Negocio.objects.filter(pk=negocio.pk).exists()
