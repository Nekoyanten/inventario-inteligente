"""Un usuario nunca debe ver ni tocar datos de otro negocio."""

import pytest
from django.core.exceptions import PermissionDenied
from django.http import Http404

from apps.catalogo.models import Producto
from apps.core.models import Giro, Negocio
from apps.core.negocio import del_negocio, obtener_del_negocio
from apps.inventario.models import Lote, TipoMovimiento
from apps.inventario.services import registrar_movimiento
from apps.usuarios.models import Rol, Usuario


@pytest.fixture
def otro_negocio(db):
    return Negocio.objects.create(nombre="Competencia", giro=Giro.MINIMERCADO)


@pytest.fixture
def producto_ajeno(otro_negocio):
    return Producto.objects.create(negocio=otro_negocio, sku="SECRETO", nombre="Producto ajeno", precio_compra=999)


@pytest.fixture
def admin_ajeno(otro_negocio):
    return Usuario.objects.create_user("ajeno", password="x", negocio=otro_negocio, rol=Rol.ADMIN)


def test_del_negocio_filtra_modelos_con_fk_directa(producto, producto_ajeno):
    assert list(del_negocio(producto.negocio, Producto)) == [producto]


def test_del_negocio_filtra_modelos_indirectos(producto, producto_ajeno, admin, admin_ajeno):
    registrar_movimiento(producto=producto, tipo=TipoMovimiento.ENTRADA_INICIAL, cantidad=5, usuario=admin)
    registrar_movimiento(producto=producto_ajeno, tipo=TipoMovimiento.ENTRADA_INICIAL, cantidad=5, usuario=admin_ajeno)
    lotes = del_negocio(producto.negocio, Lote)
    assert lotes.count() == 1 and lotes.first().producto == producto


def test_obtener_de_otro_negocio_da_404(producto, producto_ajeno):
    with pytest.raises(Http404):
        obtener_del_negocio(producto.negocio, Producto, pk=producto_ajeno.pk)


def test_sin_negocio_no_hay_acceso(db):
    with pytest.raises(PermissionDenied):
        del_negocio(None, Producto)


def test_dashboard_no_mezcla_negocios(client, admin, producto, producto_ajeno):
    client.force_login(admin)
    assert client.get("/").context["resumen"]["inventario"]["productos"] == 1


def test_reporte_no_incluye_productos_ajenos(client, admin, producto, producto_ajeno):
    client.force_login(admin)
    contenido = client.get("/reportes/inventario-actual.csv").content.decode()
    assert "CAF-250" in contenido and "SECRETO" not in contenido
