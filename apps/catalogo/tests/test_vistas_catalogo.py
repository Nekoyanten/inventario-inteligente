import pytest

from apps.catalogo.models import AtributoPersonalizado, Categoria, Producto
from apps.core.models import Giro, Negocio
from apps.inventario.models import Movimiento, TipoMovimiento
from apps.usuarios.models import Rol, Usuario


@pytest.fixture
def vendedor(negocio):
    return Usuario.objects.create_user("vende", password="x", negocio=negocio, rol=Rol.VENDEDOR)


@pytest.fixture
def encargado(negocio):
    return Usuario.objects.create_user("bodega", password="x", negocio=negocio, rol=Rol.INVENTARIO)


def _producto(negocio, **extra):
    datos = {"nombre": "Arroz 1 kg", "sku": "arr-1", "precio_compra": "3200", "precio_venta": "4500",
             "stock_minimo": "10", "activo": "on", "stock_inicial": "25"}
    datos.update(extra)
    return datos


def test_crear_producto_con_stock_inicial(client, admin, negocio):
    client.force_login(admin)
    resp = client.post("/productos/nuevo/", _producto(negocio))
    p = Producto.objects.get(sku="ARR-1")  # el SKU se normaliza en mayúsculas
    assert resp.status_code == 302 and p.stock_actual == 25
    assert Movimiento.objects.get(producto=p).tipo == TipoMovimiento.ENTRADA_INICIAL


def test_sku_repetido_y_venta_a_perdida(client, admin, producto):
    client.force_login(admin)
    resp = client.post("/productos/nuevo/", _producto(producto.negocio, sku="caf-250", precio_venta="100"))
    html = resp.content.decode()
    assert "Ya existe un producto" in html and "pérdida" in html


def test_atributos_personalizados_se_guardan(client, admin, negocio):
    cat = Categoria.objects.create(negocio=negocio, nombre="Camisas")
    talla = AtributoPersonalizado.objects.create(categoria=cat, nombre="Talla", tipo="OPCION", opciones=["S", "M"])
    client.force_login(admin)
    client.post("/productos/nuevo/", _producto(negocio, categoria=cat.pk, **{f"atributo__{talla.pk}": "M"}))
    assert Producto.objects.get(sku="ARR-1").atributos == {"Talla": "M"}


def test_encargado_no_ve_ni_edita_costos(client, encargado, producto):
    client.force_login(encargado)
    html = client.get(f"/productos/{producto.pk}/editar/").content.decode()
    assert "precio_compra" not in html
    assert "Costo" not in client.get("/productos/").content.decode()


def test_lista_filtra_por_estado(client, admin, producto):
    client.force_login(admin)
    assert len(client.get("/productos/?estado=AGOTADO").context["pagina"]) == 1
    assert len(client.get("/productos/?estado=NORMAL").context["pagina"]) == 0


def test_busqueda_json_no_expone_otro_negocio(client, vendedor, producto):
    otro = Negocio.objects.create(nombre="Otro", giro=Giro.GENERICO)
    Producto.objects.create(negocio=otro, sku="CAF-X", nombre="Café ajeno")
    client.force_login(vendedor)
    nombres = [r["nombre"] for r in client.get("/productos/buscar.json?q=café").json()["resultados"]]
    assert nombres == ["Café 250 g"]


def test_generar_variantes(client, admin, negocio):
    padre = Producto.objects.create(negocio=negocio, sku="CAM", nombre="Camisa", precio_venta=50000)
    client.force_login(admin)
    client.post(f"/productos/{padre.pk}/variantes/", {"valores__Variante": "S, M, L"})
    padre.refresh_from_db()
    assert padre.es_agrupador and padre.variantes.count() == 3
    assert set(padre.variantes.values_list("sku", flat=True)) == {"CAM-S", "CAM-M", "CAM-L"}


def test_detalle_producto(client, admin, producto):
    client.force_login(admin)
    html = client.get(f"/productos/{producto.pk}/").content.decode()
    assert "Ritmo de ventas" in html and "Kárdex" in html or "kárdex" in html
