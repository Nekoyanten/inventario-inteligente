"""Menú principal: se arma según los permisos del rol y las rutas instaladas.

Cada entrada: (permiso, nombre_url, icono, texto, apps_que_la_activan)
"""

from django.urls import NoReverseMatch, reverse

MENU = [
    (None, "dashboard:inicio", "🏠", "Inicio", {"dashboard"}),
    ("atender_mesas", "nocturno:mis_mesas", "🍽️", "Mis mesas", {"nocturno:mis_mesas"}),
    ("cobrar_cuentas", "nocturno:noche", "🍸", "La noche", {"nocturno"}),
    ("registrar_venta", "ventas:pos", "🧾", "Vender", {"ventas:pos"}),
    ("consultar_productos", "catalogo:lista", "📦", "Productos", {"catalogo"}),
    ("registrar_movimiento", "inventario:movimiento", "🔁", "Inventario", {"inventario"}),
    ("registrar_venta", "ventas:lista", "💵", "Ventas", {"ventas:lista", "ventas:detalle"}),
    ("gestionar_clientes", "clientes:panel", "💛", "Clientes", {"clientes"}),
    ("ver_reportes", "alertas:lista", "🚨", "Alertas", {"alertas"}),
    ("gestionar_compras", "recomendaciones:lista", "🛒", "Compras", {"recomendaciones", "compras"}),
    ("gestionar_proveedores", "proveedores:lista", "🚚", "Proveedores", {"proveedores"}),
    ("ver_reportes", "reportes:inicio", "📊", "Reportes", {"reportes"}),
    ("gestionar_usuarios", "usuarios:lista", "👥", "Equipo", {"usuarios"}),
    ("configurar_negocio", "negocio:configuracion", "⚙️", "Ajustes", {"negocio"}),
]

DESCRIPCIONES = {
    "nocturno:mis_mesas": "Abrir mesas y tomar pedidos",
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

    for permiso, nombre, icono, texto, activa in MENU:
        if permiso and permiso not in permisos:
            continue
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
