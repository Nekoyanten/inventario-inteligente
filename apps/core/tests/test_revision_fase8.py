"""Correcciones hechas al integrar la Fase 8."""

import pytest

from apps.catalogo.models import Categoria, Producto
from apps.compras.services import crear_orden
from apps.core.cierre import eliminar_negocio
from apps.core.models import Negocio
from apps.inventario.models import Movimiento, TipoMovimiento
from apps.inventario.services import ErrorInventario, registrar_movimiento
from apps.proveedores.models import Proveedor
from apps.proveedores.services import reemplazar_proveedor
from apps.usuarios.models import Usuario
from apps.ventas.services import registrar_venta

pytestmark = pytest.mark.django_db


def test_venta_con_el_mismo_producto_en_dos_lineas_calcula_el_faltante_total(negocio, admin, producto):
    registrar_movimiento(producto=producto, tipo=TipoMovimiento.ENTRADA_INICIAL, cantidad=3, usuario=admin)
    registrar_venta(negocio=negocio, vendedor=admin,
                    lineas=[{"producto": producto, "cantidad": 2}, {"producto": producto, "cantidad": 2}])
    producto.refresh_from_db()
    assert producto.stock_actual == 0
    assert Movimiento.objects.get(referencia_tipo="venta_sin_stock").cantidad == 1


def test_sin_venta_sin_stock_las_lineas_repetidas_se_suman(negocio, admin, producto):
    negocio.config.permite_venta_sin_stock = False
    negocio.config.save()
    registrar_movimiento(producto=producto, tipo=TipoMovimiento.ENTRADA_INICIAL, cantidad=3, usuario=admin)
    with pytest.raises(ErrorInventario, match="se piden 4"):
        registrar_venta(negocio=negocio, vendedor=admin,
                        lineas=[{"producto": producto, "cantidad": 2}, {"producto": producto, "cantidad": 2}])


def test_venta_rechaza_productos_de_otro_negocio(negocio, admin):
    ajeno = Producto.objects.create(negocio=Negocio.objects.create(nombre="Otro"), sku="X", nombre="Ajeno")
    with pytest.raises(ErrorInventario, match="no pertenece"):
        registrar_venta(negocio=negocio, vendedor=admin, lineas=[{"producto": ajeno, "cantidad": 1}])


def test_cerrar_cuenta_no_borra_al_duenio_de_la_plataforma(negocio, admin):
    dueno = Usuario.objects.create_superuser("dueno", "d@d.co", "x", negocio=negocio)
    eliminar_negocio(negocio)
    dueno.refresh_from_db()
    assert dueno.negocio is None and not Usuario.objects.filter(pk=admin.pk).exists()


def test_cambio_de_proveedor_por_categoria_no_mueve_ordenes_mixtas(negocio, admin, proveedor):
    cat, otra = list(Categoria.objects.filter(negocio=negocio)[:2])
    nuevo = Proveedor.objects.create(negocio=negocio, nombre="Nuevo")
    cambia = Producto.objects.create(negocio=negocio, sku="A", nombre="A", categoria=cat, proveedor_principal=proveedor)
    queda = Producto.objects.create(negocio=negocio, sku="B", nombre="B", categoria=otra, proveedor_principal=proveedor)
    solo_cambia = crear_orden(negocio=negocio, proveedor=proveedor, usuario=admin,
                              lineas=[{"producto": cambia, "cantidad": 1, "costo": 1}])
    mixta = crear_orden(negocio=negocio, proveedor=proveedor, usuario=admin,
                        lineas=[{"producto": cambia, "cantidad": 1, "costo": 1},
                                {"producto": queda, "cantidad": 1, "costo": 1}])
    r = reemplazar_proveedor(origen=proveedor, destino=nuevo, usuario=admin, categoria=cat)
    solo_cambia.refresh_from_db()
    mixta.refresh_from_db()
    assert r["borradores_movidos"] == 1
    assert solo_cambia.proveedor == nuevo and mixta.proveedor == proveedor  # la mixta sigue con quien surte a «B»
