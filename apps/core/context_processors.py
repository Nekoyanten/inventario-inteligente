from apps.usuarios.permisos import PERMISOS_POR_ROL


def negocio(request):
    """Expone el negocio, su configuración y los permisos del usuario a todas las plantillas.

    En plantillas:  {% if "gestionar_usuarios" in permisos %} … {% endif %}
    """
    neg = getattr(request, "negocio", None)
    usuario = getattr(request, "user", None)
    permisos = set()
    if usuario is not None and usuario.is_authenticated:
        permisos = set().union(*PERMISOS_POR_ROL.values()) if usuario.is_superuser else PERMISOS_POR_ROL.get(usuario.rol, set())
    return {
        "negocio": neg,
        "config_negocio": getattr(neg, "config", None) if neg else None,
        "permisos": permisos,
    }
