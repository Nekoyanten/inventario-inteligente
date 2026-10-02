"""Menú principal: se arma según los permisos del rol y las rutas instaladas.

Cada entrada: (permiso, nombre_url, icono, texto, apps_que_la_activan)
"""

from django.urls import NoReverseMatch, reverse

MENU = [
    (None, "dashboard:inicio", "house", "Inicio", {"dashboard"}),
    ("atender_mesas", "nocturno:mis_mesas", "armchair", "Mesas", {"nocturno:mis_mesas", "nocturno:cuenta"}),
    ("cobrar_cuentas", "nocturno:noche", "wine", "La noche", {"nocturno"}),
    ("registrar_venta", "ventas:pos", "receipt", "Vender", {"ventas:pos"}),
    ("consultar_productos", "catalogo:lista", "package", "Productos", {"catalogo"}),
    ("registrar_movimiento", "inventario:movimiento", "arrow-left-right", "Inventario", {"inventario"}),
    ("registrar_venta", "ventas:lista", "banknote", "Ventas", {"ventas:lista", "ventas:detalle"}),
    ("gestionar_clientes", "clientes:panel", "heart-handshake", "Clientes", {"clientes"}),
    ("ver_reportes", "alertas:lista", "bell-ring", "Alertas", {"alertas"}),
    ("gestionar_compras", "recomendaciones:lista", "shopping-cart", "Compras", {"recomendaciones", "compras"}),
    ("gestionar_proveedores", "proveedores:lista", "truck", "Proveedores", {"proveedores"}),
    ("ver_reportes", "reportes:inicio", "chart-column", "Reportes", {"reportes"}),
    ("gestionar_usuarios", "usuarios:lista", "users", "Equipo", {"usuarios"}),
    ("configurar_negocio", "negocio:configuracion", "settings", "Ajustes", {"negocio"}),
]

DESCRIPCIONES = {
    "nocturno:mis_mesas": "Tomar mesas, pedidos y cobrar",
    "nocturno:noche": "Cobrar cuentas, puerta y reservas",
    "ventas:pos": "Cobrar una venta",
    "catalogo:lista": "Precios y cuánto hay",
    "inventario:movimiento": "Entradas, daños y conteos",
    "ventas:lista": "Ventas hechas",
    "clientes:panel": "Puntos y clientes frecuentes",
    "alertas:lista": "Lo que necesita atención",
    "recomendaciones:lista": "Qué pedir al proveedor",
    "proveedores:lista": "Datos de tus proveedores",
    "reportes:inicio": "Cómo va el negocio",
    "usuarios:lista": "Quién entra y qué ve",
    "negocio:configuracion": "Datos, colores y plan",
}


def construir_menu(request, permisos, contadores=None):
    contadores = contadores or {}
    match = getattr(request, "resolver_match", None)
    app = match.app_name if match else ""
    vista = f"{app}:{match.url_name}" if match else ""
    items = []
    negocio = getattr(request, "negocio", None)
    nocturno = getattr(negocio, "giro", "") in ("BAR", "DISCOTECA", "BAR_DISCOTECA")
    suscripcion = getattr(request, "suscripcion", None)
    from .modulos import modulo_de_menu

    solo_mesero = "atender_mesas" in permisos and not ({"cobrar_cuentas", "registrar_venta"} & set(permisos))
    for permiso, nombre, icono, texto, activa in MENU:
        if permiso and permiso not in permisos:
            continue
        if nombre == "dashboard:inicio" and solo_mesero and nocturno:
            continue  # su inicio son las mesas
        modulo = modulo_de_menu(nombre)
        if modulo and suscripcion is not None and not suscripcion.tiene_modulo(modulo):
            continue  # no está en su plan
        if nombre.startswith("nocturno:") and not nocturno:
            continue  # solo bares y discotecas
        if nombre == "nocturno:mis_mesas" and "cobrar_cuentas" in permisos:
            continue  # el cajero y el dueño ven todas las mesas en «La noche»
        try:
            url = reverse(nombre)
        except NoReverseMatch:
            continue  # módulo aún no instalado
        items.append({
            "url": url, "icono": icono, "texto": texto,
            "activo": app in activa or vista in activa,
            "contador": contadores.get(nombre), "nombre": nombre, "descripcion": DESCRIPCIONES.get(nombre, ""),
        })
    # En el celular caben 5 botones abajo: los primeros 4 y «Más» con el resto
    for i, item in enumerate(items):
        item["principal"] = len(items) <= 5 or i < 4
    return items
