from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from apps.core.negocio import del_negocio, negocio_requerido, obtener_del_negocio
from apps.core.seguridad import url_segura as _url_segura
from apps.usuarios.permisos import requiere_permiso

from .models import Alerta
from .motor import evaluar_negocio
from .selectors import bandeja_hoy
from .silencio import SILENCIABLES, describir, reactivar, silenciar

ABIERTAS = [Alerta.Estado.ABIERTA, Alerta.Estado.VISTA]


@negocio_requerido
@requiere_permiso("ver_reportes")
def lista(request):
    estado = request.GET.get("estado", "abiertas")
    if estado == "abiertas" and not request.GET.get("tipo") and request.GET.get("vista", "hoy") == "hoy":
        return _hoy(request)
    qs = del_negocio(request.negocio, Alerta).select_related("producto__categoria")
    qs = qs.filter(estado__in=ABIERTAS) if estado == "abiertas" else qs.exclude(estado__in=ABIERTAS)
    if request.GET.get("tipo"):
        qs = qs.filter(tipo=request.GET["tipo"])
    alertas = list(qs[:300])
    grupos = [
        ("Actuar", [a for a in alertas if a.severidad == Alerta.Severidad.ACTUAR]),
        ("Revisar", [a for a in alertas if a.severidad == Alerta.Severidad.REVISAR]),
        ("Para tener en cuenta", [a for a in alertas if a.severidad == Alerta.Severidad.INFO]),
    ]
    # Al abrir la bandeja, las nuevas pasan a "vistas"
    if estado == "abiertas":
        del_negocio(request.negocio, Alerta).filter(estado=Alerta.Estado.ABIERTA, pk__in=[a.pk for a in alertas]).update(
            estado=Alerta.Estado.VISTA)
    return render(request, "alertas/lista.html", {"grupos": grupos, "tipos": Alerta.Tipo.choices, "estado": estado,
                                                  "total": len(alertas), "abierta": estado == "abiertas",
                                                  "silenciables": SILENCIABLES})


def _hoy(request):
    """Bandeja por defecto: las 10 alertas que importan hoy + resumen de baja rotación y exceso."""
    datos = bandeja_hoy(request.negocio)
    del_negocio(request.negocio, Alerta).filter(estado=Alerta.Estado.ABIERTA, pk__in=[a.pk for a in datos["hoy"]]).update(
        estado=Alerta.Estado.VISTA)
    return render(request, "alertas/hoy.html", {**datos, "silenciadas": describir(request.negocio),
                                                "silenciables": SILENCIABLES, "abierta": True})


@negocio_requerido
@requiere_permiso("configurar_negocio")
@require_POST
def silenciar_alertas(request):
    tipo = request.POST.get("tipo", "")
    categoria = request.POST.get("categoria") or None
    if categoria is not None:
        from apps.catalogo.models import Categoria

        categoria = obtener_del_negocio(request.negocio, Categoria, pk=categoria).pk
    try:
        n = silenciar(request.negocio, request.user, tipo, categoria)
    except ValueError as e:
        messages.error(request, str(e))
    else:
        messages.success(request, f"Listo: no volverás a ver «{Alerta.Tipo(tipo).label}» ahí ({n} cerradas). "
                                  "Puedes reactivarlas cuando quieras.")
    return redirect(_url_segura(request, request.POST.get("volver")) or "alertas:lista")


@negocio_requerido
@requiere_permiso("configurar_negocio")
@require_POST
def reactivar_alertas(request):
    categoria = request.POST.get("categoria") or None
    try:
        categoria = int(categoria) if categoria else None
    except ValueError:
        categoria = None
    reactivar(request.negocio, request.user, request.POST.get("tipo", ""), categoria)
    messages.success(request, "Alertas reactivadas; aparecerán en el próximo análisis.")
    return redirect("alertas:lista")


@negocio_requerido
@requiere_permiso("ver_reportes")
@require_POST
def cambiar_estado(request, pk):
    alerta = obtener_del_negocio(request.negocio, Alerta, pk=pk)
    nuevo = request.POST.get("estado")
    if nuevo in (Alerta.Estado.RESUELTA, Alerta.Estado.DESCARTADA):
        alerta.estado = nuevo
        alerta.resuelta_por = request.user
        alerta.nota = request.POST.get("nota", "")[:255]
        alerta.save(update_fields=["estado", "resuelta_por", "nota", "actualizado"])
        messages.success(request, "Alerta " + ("resuelta." if nuevo == Alerta.Estado.RESUELTA else "descartada."))
    return redirect(_url_segura(request, request.POST.get("volver")) or "alertas:lista")


@negocio_requerido
@requiere_permiso("configurar_negocio")
@require_POST
def analizar(request):
    n = evaluar_negocio(request.negocio)
    messages.success(request, f"Análisis completado: {n} alertas vigentes.")
    return redirect("alertas:lista")
