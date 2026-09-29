"""Módulos que el administrador de la plataforma puede prender o apagar para cada negocio (plan a la medida)."""

MODULOS = {
    # clave: (nombre, rutas que abre, entradas del menú)
    "clientes": ("💛 Clientes y fidelización", ("/clientes/",), ("clientes:panel",)),
    "nocturno": ("🍸 La noche (cuentas, puerta, reservas, botellas)", ("/noche/",), ("nocturno:noche",)),
    "compras": ("🛒 Compras y proveedores", ("/compras/", "/proveedores/"), ("recomendaciones:lista", "proveedores:lista")),
    "reportes": ("📊 Reportes", ("/reportes/",), ("reportes:inicio",)),
}


def modulo_de_ruta(path: str) -> str | None:
    for clave, (_, rutas, _) in MODULOS.items():
        if path.startswith(rutas):
            return clave
    return None


def modulo_de_menu(nombre_url: str) -> str | None:
    for clave, (_, _, menu) in MODULOS.items():
        if nombre_url in menu:
            return clave
    return None
