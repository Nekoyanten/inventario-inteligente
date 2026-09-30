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
def apariencia(request):
    """Color de la marca, modo claro/oscuro, letra grande y logo del negocio."""
    from .apariencia import PALETAS
    from .forms import AparienciaForm

    config = request.negocio.config
    form = AparienciaForm(request.POST or None, request.FILES or None, instance=config)
    if request.method == "POST" and request.POST.get("quitar_logo"):
        config.logo = None
        config.save(update_fields=["logo"])
        messages.success(request, "Se quitó el logo.")
        return redirect("negocio:apariencia")
    if request.method == "POST" and form.is_valid():
        form.save()
        auditar(request.negocio, request.user, "cambiar_apariencia", config, cambios=form.changed_data)
        messages.success(request, "Listo: así se ve ahora tu negocio.")
        return redirect("negocio:apariencia")
    return render(request, "negocio/apariencia.html", {"form": form, "paletas": PALETAS, "config": config})


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


@negocio_requerido
@requiere_permiso("configurar_negocio")
def temporadas(request):
    from django import forms as dj_forms

    from apps.analitica.models import Temporada
    from apps.catalogo.models import Categoria

    class TemporadaForm(dj_forms.ModelForm):
        class Meta:
            model = Temporada
            fields = ("nombre", "inicio_dia", "inicio_mes", "fin_dia", "fin_mes", "factor", "categoria")
            labels = {"inicio_dia": "Día de inicio", "inicio_mes": "Mes de inicio", "fin_dia": "Día final",
                      "fin_mes": "Mes final", "factor": "Factor de demanda (1.5 = +50 %)",
                      "categoria": "Solo para la categoría (opcional)"}

        def clean(self):
            d = super().clean()
            for campo, maximo in (("inicio_mes", 12), ("fin_mes", 12), ("inicio_dia", 31), ("fin_dia", 31)):
                if d.get(campo) is not None and not 1 <= d[campo] <= maximo:
                    self.add_error(campo, f"Debe estar entre 1 y {maximo}.")
            return d

    form = TemporadaForm(request.POST or None)
    form.fields["categoria"].queryset = del_negocio(request.negocio, Categoria)
    if request.method == "POST":
        if request.POST.get("eliminar"):
            del_negocio(request.negocio, Temporada).filter(pk=request.POST["eliminar"]).delete()
            return redirect("negocio:temporadas")
        if form.is_valid():
            t = form.save(commit=False)
            t.negocio = request.negocio
            t.save()
            messages.success(request, f"Temporada {t.nombre} agregada.")
            return redirect("negocio:temporadas")
    return render(request, "negocio/temporadas.html", {
        "form": form, "temporadas": del_negocio(request.negocio, Temporada).select_related("categoria"),
    })


@negocio_requerido
@requiere_permiso("configurar_negocio")
def api_token(request):
    from rest_framework.authtoken.models import Token

    token = Token.objects.filter(user=request.user).first()
    if request.method == "POST":
        Token.objects.filter(user=request.user).delete()
        token = Token.objects.create(user=request.user)
        auditar(request.negocio, request.user, "generar_token_api", request.user)
        messages.success(request, "Nuevo token generado. El anterior dejó de funcionar.")
    return render(request, "negocio/api.html", {"token": token})


@negocio_requerido
def plan(request):
    from django.conf import settings

    from apps.catalogo.models import Producto
    from apps.usuarios.models import Usuario as U

    s = request.suscripcion
    uso = {"productos": Producto.objects.filter(negocio=request.negocio, es_agrupador=False).count(),
           "usuarios": U.objects.filter(negocio=request.negocio, is_active=True).count()}
    from .modulos import MODULOS

    modulos = [{"nombre": v[0], "activo": s.tiene_modulo(k)} for k, v in MODULOS.items()
               if k != "nocturno" or request.negocio.giro in ("BAR", "DISCOTECA", "BAR_DISCOTECA")]
    return render(request, "negocio/plan.html", {"s": s, "uso": uso, "modulos": modulos,
                                                 "contacto": settings.CONTACTO_VENTAS})


@negocio_requerido
@requiere_permiso("configurar_negocio")
def cerrar_cuenta(request):
    """Borra el negocio y todos sus datos. Solo el administrador, con su contraseña y el nombre del negocio."""
    from django.contrib.auth import logout

    from .cierre import eliminar_negocio
    from .forms import CerrarCuentaForm

    form = CerrarCuentaForm(request.POST or None, negocio=request.negocio, usuario=request.user)
    if request.method == "POST" and form.is_valid():
        eliminar_negocio(request.negocio)
        logout(request)
        messages.success(request, "Tu cuenta y todos los datos de tu negocio fueron eliminados. Gracias por usarnos.")
        return redirect("/")
    return render(request, "negocio/cerrar_cuenta.html", {"form": form})
