"""Configuración del negocio y bitácora de auditoría (solo administrador)."""

from django.contrib import messages
from django.core.paginator import Paginator
from django.shortcuts import redirect, render

from apps.usuarios.models import Usuario
from apps.usuarios.permisos import requiere_permiso

from .auditoria import auditar
from .forms import ConfiguracionForm, NegocioForm
from .models import RegistroAuditoria
from .negocio import del_negocio, negocio_requerido
from .plantillas import aplicar_plantilla


@negocio_requerido
@requiere_permiso("configurar_negocio")
def configuracion(request):
    negocio = request.negocio
    form_negocio = NegocioForm(request.POST or None, instance=negocio, prefix="n")
    form_config = ConfiguracionForm(request.POST or None, instance=negocio.config, prefix="c")
    if request.method == "POST" and form_negocio.is_valid() and form_config.is_valid():
        form_negocio.save()
        form_config.save()
        auditar(negocio, request.user, "configurar_negocio", negocio,
                cambios=form_negocio.changed_data + form_config.changed_data)
        messages.success(request, "Configuración guardada.")
        return redirect("negocio:configuracion")
    return render(request, "negocio/configuracion.html", {"form_negocio": form_negocio, "form_config": form_config})


@negocio_requerido
@requiere_permiso("configurar_negocio")
def restaurar_plantilla(request):
    """Vuelve a aplicar la plantilla del giro (no borra nada: solo agrega categorías faltantes)."""
    if request.method == "POST":
        aplicar_plantilla(request.negocio)
        auditar(request.negocio, request.user, "restaurar_plantilla", request.negocio)
        messages.success(request, "Se restauró la configuración recomendada para tu tipo de negocio.")
    return redirect("negocio:configuracion")


@negocio_requerido
@requiere_permiso("configurar_negocio")
def auditoria(request):
    qs = del_negocio(request.negocio, RegistroAuditoria).select_related("usuario")
    f = request.GET
    if f.get("usuario"):
        qs = qs.filter(usuario_id=f["usuario"])
    if f.get("accion"):
        qs = qs.filter(accion=f["accion"])
    if f.get("desde"):
        qs = qs.filter(fecha__date__gte=f["desde"])
    if f.get("hasta"):
        qs = qs.filter(fecha__date__lte=f["hasta"])
    pagina = Paginator(qs, 50).get_page(f.get("pagina"))
    return render(request, "negocio/auditoria.html", {
        "pagina": pagina,
        "usuarios": del_negocio(request.negocio, Usuario).order_by("username"),
        "acciones": del_negocio(request.negocio, RegistroAuditoria).values_list("accion", flat=True)
        .distinct().order_by("accion"),
    })
