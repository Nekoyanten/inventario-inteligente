from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .selectors import resumen_negocio, resumen_vendedor


@login_required
def inicio(request):
    if request.negocio is None:
        return render(request, "dashboard/sin_negocio.html")
    if request.user.puede("ver_reportes"):
        return render(request, "dashboard/inicio.html", {"resumen": resumen_negocio(request.negocio)})
    if request.user.puede("registrar_venta"):
        return render(request, "dashboard/vendedor.html", {"resumen": resumen_vendedor(request.negocio, request.user)})
    return redirect("catalogo:lista")
