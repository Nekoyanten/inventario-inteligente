"""Menú principal: se arma según los permisos del rol y las rutas instaladas.

Cada entrada: (permiso, nombre_url, icono, texto, apps_que_la_activan)
"""

from django.urls import NoReverseMatch, reverse

MENU = [
    (None, "dashboard:inicio", "🏠", "Inicio", {"dashboard"}),
    ("registrar_venta", "ventas:pos", "🧾", "Vender", {"ventas:pos"}),
    ("consultar_productos", "catalogo:lista", "📦", "Productos", {"catalogo"}),
    ("registrar_movimiento", "inventario:movimiento", "🔁", "Inventario", {"inventario"}),
    ("ver_reportes", "alertas:lista", "🚨", "Alertas", {"alertas"}),
    ("gestionar_compras", "recomendaciones:lista", "🛒", "Compras", {"recomendaciones", "compras"}),
    ("gestionar_proveedores", "proveedores:lista", "🚚", "Proveedores", {"proveedores"}),
    ("registrar_venta", "ventas:lista", "💵", "Ventas", {"ventas:lista", "ventas:detalle"}),
    ("ver_reportes", "reportes:inicio", "📊", "Reportes", {"reportes"}),
    ("gestionar_usuarios", "usuarios:lista", "👥", "Usuarios", {"usuarios"}),
    ("configurar_negocio", "negocio:configuracion", "⚙️", "Ajustes", {"negocio"}),
]


def construir_menu(request, permisos, contadores=None):
    contadores = contadores or {}
    match = getattr(request, "resolver_match", None)
    app = match.app_name if match else ""
    vista = f"{app}:{match.url_name}" if match else ""
    items = []
    for permiso, nombre, icono, texto, activa in MENU:
        if permiso and permiso not in permisos:
            continue
        try:
            url = reverse(nombre)
        except NoReverseMatch:
            continue  # módulo aún no instalado
        items.append({
            "url": url, "icono": icono, "texto": texto,
            "activo": app in activa or vista in activa,
            "contador": contadores.get(nombre),
        })
    return items
