"""Matriz de permisos por rol (ver docs/DISENO.md §8).

Uso en vistas:  @requiere_permiso("registrar_venta")
"""

from functools import wraps

from django.core.exceptions import PermissionDenied

from .models import Rol

PERMISOS_POR_ROL = {
    Rol.ADMIN: {
        "configurar_negocio",
        "gestionar_usuarios",
        "gestionar_productos",
        "ver_precios_compra",
        "consultar_productos",
        "registrar_venta",
        "registrar_movimiento",
        "registrar_conteo",
        "aprobar_ajuste",
        "gestionar_compras",
        "gestionar_proveedores",
        "ver_reportes",
        "ver_reportes_financieros",
    },
    Rol.VENDEDOR: {"consultar_productos", "registrar_venta"},
    Rol.INVENTARIO: {
        "gestionar_productos",
        "consultar_productos",
        "registrar_movimiento",
        "registrar_conteo",
        "gestionar_compras",
        "ver_reportes",
    },
}


def requiere_permiso(accion):
    def decorador(vista):
        @wraps(vista)
        def envoltura(request, *args, **kwargs):
            if not request.user.is_authenticated or not request.user.puede(accion):
                raise PermissionDenied
            return vista(request, *args, **kwargs)

        return envoltura

    return decorador
