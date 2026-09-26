import pytest

from apps.catalogo.models import Categoria, Producto
from apps.core.models import Giro, Negocio
from apps.proveedores.models import Proveedor
from apps.usuarios.models import Rol, Usuario


@pytest.fixture
def negocio(db):
    return Negocio.objects.create(nombre="Tienda Test", giro=Giro.MINIMERCADO)


@pytest.fixture
def admin(negocio):
    return Usuario.objects.create_user("admin", password="x", negocio=negocio, rol=Rol.ADMIN)


@pytest.fixture
def proveedor(negocio):
    return Proveedor.objects.create(negocio=negocio, nombre="Proveedor A", tiempo_entrega_dias=4)


@pytest.fixture
def producto(negocio, proveedor):
    return Producto.objects.create(
        negocio=negocio,
        sku="CAF-250",
        nombre="Café 250 g",
        categoria=Categoria.objects.filter(negocio=negocio).first(),
        precio_compra=8500,
        precio_venta=12000,
        stock_minimo=8,
        proveedor_principal=proveedor,
    )
