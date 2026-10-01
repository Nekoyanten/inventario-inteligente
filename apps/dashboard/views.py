from django.shortcuts import redirect, render

from .selectors import resumen_equipo, resumen_negocio


def inicio(request):
    if not request.user.is_authenticated:
        from django.conf import settings

        planes = [{"clave": k, **v} for k, v in settings.PLANES.items()]
        return render(request, "publico/inicio.html", {"planes": planes, "dias_prueba": settings.DIAS_PRUEBA})
    if request.negocio is None:
        if request.user.is_superuser:  # el administrador de la plataforma empieza en su panel
            return redirect("plataforma:panel")
        return render(request, "dashboard/sin_negocio.html")
    u = request.user
    if u.puede("configurar_negocio"):  # el dueño: cómo va todo el negocio
        from apps.core.arranque import progreso_arranque

        return render(request, "dashboard/inicio.html", {"resumen": resumen_negocio(request.negocio),
                                                         "arranque": progreso_arranque(request.negocio)})
    if u.puede("atender_mesas") and not u.puede("cobrar_cuentas") and not u.puede("registrar_venta"):
        return redirect("nocturno:mis_mesas")  # el mesero va directo a sus mesas
    # El resto del equipo: botones grandes con lo suyo y un resumen corto de lo que le toca
    from apps.core.context_processors import negocio as contexto

    atajos = [i for i in contexto(request)["menu"] if i["nombre"] != "dashboard:inicio"]
    if atajos:
        atajos[0]["principal_inicio"] = True
    return render(request, "dashboard/equipo.html", {"atajos": atajos, "resumen": resumen_equipo(request.negocio, u)})
