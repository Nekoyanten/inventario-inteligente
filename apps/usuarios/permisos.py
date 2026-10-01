"""Quién puede hacer qué (ver docs/DISENO.md §8).

El dueño (rol Administrador) ve todo. Los demás ven solo sus «áreas»: cada rol trae unas por defecto y el dueño
puede marcar o quitar áreas a cada persona. Cada área abre un grupo de permisos.

Uso en vistas:  @requiere_permiso("registrar_venta")
"""

from functools import wraps

from django.core.exceptions import PermissionDenied

from .models import Rol

NOCTURNOS = ("BAR", "DISCOTECA", "BAR_DISCOTECA")

# clave: (nombre, para qué sirve, permisos que abre, módulo del plan que necesita o None)
AREAS = {
    "vender": ("🧾 Vender en caja", "Cobrar en la caja rápida y ver sus ventas.",
               {"registrar_venta", "consultar_productos", "registrar_cliente"}, None),
    "mesas": ("🍽️ Atender mesas", "Abrir sus mesas, tomar pedidos y pedir la cuenta. No cobra.",
              {"atender_mesas", "consultar_productos", "registrar_cliente"}, "nocturno"),
    "caja": ("💵 Caja de la noche", "Ver todas las cuentas, cobrar, puerta, reservas y botellas guardadas.",
             {"cobrar_cuentas", "atender_mesas", "registrar_venta", "consultar_productos", "registrar_cliente"},
             "nocturno"),
    "productos": ("📦 Productos", "Crear y editar productos y precios de venta.",
                  {"consultar_productos", "gestionar_productos"}, None),
    "inventario": ("🔁 Inventario", "Registrar entradas, salidas, daños y conteos.",
                   {"consultar_productos", "registrar_movimiento", "registrar_conteo"}, None),
    "compras": ("🛒 Compras y proveedores", "Ver qué pedir, hacer pedidos y recibir mercancía.",
                {"consultar_productos", "gestionar_compras", "gestionar_proveedores"}, "compras"),
    "clientes": ("💛 Clientes y fidelización", "Puntos, ofertas y clientes frecuentes.",
                 {"registrar_cliente", "gestionar_clientes"}, "clientes"),
    "reportes": ("📊 Reportes y alertas", "Ver cómo va el negocio, alertas y reportes (sin costos ni utilidad).",
                 {"ver_reportes"}, None),
}

# Solo el dueño / administrador
PERMISOS_DUENO = {"configurar_negocio", "gestionar_usuarios", "ver_precios_compra", "ver_reportes_financieros",
                  "aprobar_ajuste", "asignar_mesas"}

ROLES_INFO = {
    Rol.ADMIN: "Ve y maneja todo el negocio.",
    Rol.CAJERO: "Cobra: caja rápida y, en bares, las cuentas de las mesas.",
    Rol.MESERO: "Solo sus mesas: abre, toma pedidos y pide la cuenta.",
    Rol.VENDEDOR: "Vende en la caja y consulta productos.",
    Rol.INVENTARIO: "Productos, inventario, compras y alertas.",
}


def areas_por_defecto(rol: str, giro: str = "") -> list[str]:
    nocturno = giro in NOCTURNOS
    if rol == Rol.ADMIN:
        return list(AREAS)
    if rol == Rol.MESERO:
        return ["mesas"]
    if rol == Rol.CAJERO:
        return ["vender", "caja"] if nocturno else ["vender"]
    if rol == Rol.INVENTARIO:
        return ["productos", "inventario", "compras", "reportes"]
    return ["vender", "caja"] if nocturno else ["vender"]  # vendedor (en bares también cobra, como antes)


def areas_disponibles(negocio) -> list[str]:
    """Áreas que tienen sentido en este negocio (según su tipo y su plan)."""
    giro = getattr(negocio, "giro", "")
    s = getattr(negocio, "suscripcion", None) if negocio else None
    salida = []
    for clave, (_, _, _, modulo) in AREAS.items():
        if modulo == "nocturno" and giro not in NOCTURNOS:
            continue
        if modulo and s is not None and not s.tiene_modulo(modulo):
            continue
        salida.append(clave)
    return salida


def permisos_de_areas(areas) -> set[str]:
    return set().union(*(AREAS[a][2] for a in areas if a in AREAS)) if areas else set()


TODOS_LOS_PERMISOS = permisos_de_areas(AREAS) | PERMISOS_DUENO

# Compatibilidad: permisos por rol con las áreas por defecto (sin personalizar)
PERMISOS_POR_ROL = {
    Rol.ADMIN: TODOS_LOS_PERMISOS,
    **{r: permisos_de_areas(areas_por_defecto(r)) for r in (Rol.CAJERO, Rol.MESERO, Rol.VENDEDOR, Rol.INVENTARIO)},
}


def permisos_de(usuario) -> set[str]:
    if usuario is None or not usuario.is_authenticated:
        return set()
    if usuario.is_superuser or usuario.rol == Rol.ADMIN:
        return set(TODOS_LOS_PERMISOS)
    return permisos_de_areas(usuario.areas_efectivas)


def requiere_permiso(accion):
    def decorador(vista):
        @wraps(vista)
        def envoltura(request, *args, **kwargs):
            if not request.user.is_authenticated or not request.user.puede(accion):
                raise PermissionDenied
            return vista(request, *args, **kwargs)

        return envoltura

    return decorador


def requiere_alguno(*acciones):
    def decorador(vista):
        @wraps(vista)
        def envoltura(request, *args, **kwargs):
            if not request.user.is_authenticated or not any(request.user.puede(a) for a in acciones):
                raise PermissionDenied
            return vista(request, *args, **kwargs)

        return envoltura

    return decorador
