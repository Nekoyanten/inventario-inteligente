from apps.usuarios.permisos import PERMISOS_POR_ROL

from .menu import construir_menu


def negocio(request):
    """Expone negocio, configuración, permisos y menú a todas las plantillas.

    En plantillas:  {% if "gestionar_usuarios" in permisos %} … {% endif %}
    """
    neg = getattr(request, "negocio", None)
    usuario = getattr(request, "user", None)
    permisos = set()
    if usuario is not None and usuario.is_authenticated:
        if usuario.is_superuser:
            permisos = set().union(*PERMISOS_POR_ROL.values())
        else:
            permisos = PERMISOS_POR_ROL.get(usuario.rol, set())
    menu = []
    if neg is not None:
        from apps.alertas.models import Alerta

        abiertas = Alerta.objects.filter(
            negocio=neg, estado=Alerta.Estado.ABIERTA, severidad=Alerta.Severidad.ACTUAR
        ).count()
        menu = construir_menu(request, permisos, {"alertas:lista": abiertas})
    return {
        "negocio": neg,
        "config_negocio": getattr(neg, "config", None) if neg else None,
        "permisos": permisos,
        "menu": menu,
    }
