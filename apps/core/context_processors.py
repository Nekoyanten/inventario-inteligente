from .menu import construir_menu


def negocio(request):
    """Expone negocio, configuración, permisos y menú a todas las plantillas.

    En plantillas:  {% if "gestionar_usuarios" in permisos %} … {% endif %}
    """
    neg = getattr(request, "negocio", None)
    usuario = getattr(request, "user", None)
    permisos = usuario.permisos if usuario is not None and usuario.is_authenticated else set()
    menu = []
    if neg is not None:
        from apps.alertas.models import Alerta

        abiertas = Alerta.objects.filter(
            negocio=neg, estado=Alerta.Estado.ABIERTA, severidad=Alerta.Severidad.ACTUAR
        ).count()
        menu = construir_menu(request, permisos, {"alertas:lista": abiertas})
    from django.conf import settings

    from .apariencia import de_negocio

    return {
        "apariencia": de_negocio(neg),
        "empresa": settings.EMPRESA,
        "negocio": neg,
        "config_negocio": getattr(neg, "config", None) if neg else None,
        "permisos": permisos,
        "menu": menu,
    }
