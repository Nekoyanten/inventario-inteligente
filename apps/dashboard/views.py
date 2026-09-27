from django.shortcuts import redirect, render

from .selectors import resumen_negocio, resumen_vendedor


def inicio(request):
    if not request.user.is_authenticated:
        from django.conf import settings

        planes = [{"clave": k, **v} for k, v in settings.PLANES.items()]
        return render(request, "publico/inicio.html", {"planes": planes, "dias_prueba": settings.DIAS_PRUEBA})
    if request.negocio is None:
        return render(request, "dashboard/sin_negocio.html")
    if request.user.puede("ver_reportes"):
        from apps.core.arranque import progreso_arranque

        return render(request, "dashboard/inicio.html", {"resumen": resumen_negocio(request.negocio),
                                                         "arranque": progreso_arranque(request.negocio)})
    if request.user.puede("registrar_venta"):
        return render(request, "dashboard/vendedor.html", {"resumen": resumen_vendedor(request.negocio, request.user)})
    return redirect("catalogo:lista")
