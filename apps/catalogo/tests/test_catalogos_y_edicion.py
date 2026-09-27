from apps.catalogo.models import AtributoPersonalizado, Categoria, Marca, Producto
from apps.core.models import RegistroAuditoria


def test_crear_y_eliminar_categoria_marca_y_atributo(client, admin, negocio):
    client.force_login(admin)
    assert client.get("/productos/catalogos/").status_code == 200
    client.post("/productos/catalogos/", {"tipo": "categoria", "cat-nombre": "Maquillaje"})
    client.post("/productos/catalogos/", {"tipo": "marca", "mar-nombre": "Vogue"})
    cat = Categoria.objects.get(negocio=negocio, nombre="Maquillaje")
    client.post("/productos/catalogos/", {"tipo": "atributo", "atr-categoria": cat.pk, "atr-nombre": "Tono",
                                          "atr-tipo": "OPCION", "atr-opciones_texto": "Claro, Medio, Oscuro"})
    tono = AtributoPersonalizado.objects.get(categoria=cat)
    assert tono.opciones == ["Claro", "Medio", "Oscuro"] and Marca.objects.filter(nombre="Vogue").exists()
    client.post(f"/productos/catalogos/atributo/{tono.pk}/eliminar/")
    client.post(f"/productos/catalogos/categoria/{cat.pk}/eliminar/")
    assert not Categoria.objects.filter(pk=cat.pk).exists()


def test_categoria_repetida_muestra_error(client, admin, negocio):
    Categoria.objects.create(negocio=negocio, nombre="Unica")
    client.force_login(admin)
    resp = client.post("/productos/catalogos/", {"tipo": "categoria", "cat-nombre": "Unica"})
    assert resp.status_code == 200 and "Ya existe" in resp.content.decode()


def test_atributos_json_de_la_categoria(client, admin, negocio):
    cat = Categoria.objects.create(negocio=negocio, nombre="Camisas")
    AtributoPersonalizado.objects.create(categoria=cat, nombre="Talla", tipo="OPCION", opciones=["S", "M"])
    client.force_login(admin)
    datos = client.get(f"/productos/atributos/{cat.pk}/").json()["atributos"]
    assert datos[0]["nombre"] == "Talla" and datos[0]["opciones"] == ["S", "M"]


def test_editar_producto_y_desactivar(client, admin, producto):
    client.force_login(admin)
    resp = client.post(f"/productos/{producto.pk}/editar/", {
        "nombre": "Café premium", "sku": producto.sku, "precio_compra": "9000", "precio_venta": "15000",
        "stock_minimo": "8", "activo": "on"})
    assert resp.status_code == 302
    producto.refresh_from_db()
    assert producto.nombre == "Café premium" and RegistroAuditoria.objects.filter(accion="editar_producto").exists()
    client.post(f"/productos/{producto.pk}/estado/")
    producto.refresh_from_db()
    assert not producto.activo
    assert len(client.get("/productos/?activo=0").context["pagina"]) == 1


def test_crear_y_otro(client, admin):
    client.force_login(admin)
    resp = client.post("/productos/nuevo/", {"nombre": "Uno", "sku": "U1", "precio_compra": "1", "precio_venta": "2",
                                             "stock_minimo": "0", "activo": "on", "otro": "1"})
    assert resp["Location"] == "/productos/nuevo/"


def test_detalle_de_producto_agrupador(client, admin, negocio):
    padre = Producto.objects.create(negocio=negocio, sku="CAM", nombre="Camisa")
    client.force_login(admin)
    client.post(f"/productos/{padre.pk}/variantes/", {"valores__Variante": "S, M"})
    html = client.get(f"/productos/{padre.pk}/").content.decode()
    assert "Variantes" in html and "CAM-S" in html


def test_variantes_rechazadas_si_el_padre_tiene_stock(client, admin, producto):
    from apps.inventario.models import TipoMovimiento
    from apps.inventario.services import registrar_movimiento

    registrar_movimiento(producto=producto, tipo=TipoMovimiento.ENTRADA_INICIAL, cantidad=3, usuario=admin)
    client.force_login(admin)
    resp = client.post(f"/productos/{producto.pk}/variantes/", {"valores__Variante": "Rojo, Azul"})
    assert "tiene stock" in resp.content.decode()
