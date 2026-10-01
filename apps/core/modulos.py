"""Módulos que el administrador de la plataforma puede prender o apagar para cada negocio (plan a la medida)."""

MODULOS = {
    # clave: (nombre, rutas que abre, entradas del menú)
    "clientes": ("💛 Clientes y fidelización", ("/clientes/",), ("clientes:panel",)),
    "nocturno": ("🍸 La noche (cuentas, puerta, reservas, botellas)", ("/noche/",), ("nocturno:noche",)),
    "compras": ("🛒 Compras y proveedores", ("/compras/", "/proveedores/"), ("recomendaciones:lista", "proveedores:lista")),
    "reportes": ("📊 Reportes", ("/reportes/",), ("reportes:inicio",)),
}


# Siempre abiertas aunque el módulo no esté en el plan: así los datos se siguen guardando en segundo plano
# (p. ej. registrar al cliente en la caja) y, si luego activan el módulo, ya tienen todo su historial.
SEGUNDO_PLANO = ("/clientes/buscar.json", "/clientes/nuevo.json")


def modulo_de_ruta(path: str) -> str | None:
    if path.startswith(SEGUNDO_PLANO):
        return None
    for clave, (_, rutas, _) in MODULOS.items():
        if path.startswith(rutas):
            return clave
    return None


def modulo_de_menu(nombre_url: str) -> str | None:
    for clave, (_, _, menu) in MODULOS.items():
        if nombre_url in menu:
            return clave
    return None


def activo(negocio, clave: str) -> bool:
    """¿El negocio tiene este módulo en su plan? (sin suscripción = sí, p. ej. en pruebas)."""
    try:
        s = negocio.suscripcion
    except Exception:  # noqa: BLE001 — sin suscripción
        return True
    return s.tiene_modulo(clave)


def datos_guardados(negocio, clave: str) -> list[str]:
    """Lo que el negocio ya tiene guardado para ese módulo aunque no lo tenga activo (para mostrarle que no pierde nada)."""
    salida = []
    if clave == "clientes":
        from apps.clientes.models import Cliente
        from apps.ventas.models import Venta

        clientes = Cliente.objects.filter(negocio=negocio).count()
        compras = Venta.objects.filter(negocio=negocio, cliente_ref__isnull=False).count()
        if clientes:
            salida.append(f"{clientes} cliente{'s' if clientes != 1 else ''} registrados con {compras} compras")
    elif clave == "compras":
        from apps.recomendaciones.models import RecomendacionCompra as Recomendacion

        n = Recomendacion.objects.filter(negocio=negocio).count()
        if n:
            salida.append(f"{n} sugerencias de compra calculadas con tus ventas")
    elif clave == "reportes":
        from apps.ventas.models import Venta

        n = Venta.objects.filter(negocio=negocio).count()
        if n:
            salida.append(f"{n} ventas listas para analizar")
    return salida
