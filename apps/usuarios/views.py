"""Gestión de usuarios del negocio (solo administradores)."""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView

from apps.core.auditoria import auditar
from apps.core.limites import LimiteDelPlan, verificar_usuarios
from apps.core.negocio import NegocioRequeridoMixin

from .forms import UsuarioCrearForm, UsuarioEditarForm
from .models import Rol, Usuario


class UsuarioListaView(NegocioRequeridoMixin, ListView):
    model = Usuario
    permiso_requerido = "gestionar_usuarios"
    template_name = "usuarios/lista.html"
    context_object_name = "usuarios"
    ordering = ["-is_active", "first_name", "username"]

    def get_context_data(self, **kwargs):
        from .permisos import AREAS, ROLES_INFO

        ctx = super().get_context_data(**kwargs)
        for u in ctx["usuarios"]:
            u.areas_texto = "Todo" if u.es_admin else " · ".join(AREAS[a][0] for a in u.areas_efectivas if a in AREAS)
        ctx["roles"] = [(valor, nombre, ROLES_INFO.get(valor, "")) for valor, nombre in Rol.choices]
        return ctx


class UsuarioCrearView(NegocioRequeridoMixin, CreateView):
    model = Usuario
    form_class = UsuarioCrearForm
    permiso_requerido = "gestionar_usuarios"
    template_name = "usuarios/formulario.html"
    success_url = reverse_lazy("usuarios:lista")
    extra_context = {"titulo": "Nuevo usuario"}

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "negocio": self.request.negocio}

    def get_initial(self):
        rol = self.request.GET.get("rol")
        return {"rol": rol} if rol in Rol.values else {}

    def form_valid(self, form):
        try:
            verificar_usuarios(self.request.negocio)
        except LimiteDelPlan as e:
            form.add_error(None, str(e))
            return self.form_invalid(form)
        respuesta = super().form_valid(form)  # el mixin asigna el negocio
        auditar(self.request.negocio, self.request.user, "crear_usuario", self.object, rol=self.object.rol)
        messages.success(self.request, f"Usuario {self.object.username} creado.")
        return respuesta


class UsuarioEditarView(NegocioRequeridoMixin, UpdateView):
    model = Usuario
    form_class = UsuarioEditarForm
    permiso_requerido = "gestionar_usuarios"
    template_name = "usuarios/formulario.html"
    success_url = reverse_lazy("usuarios:lista")
    extra_context = {"titulo": "Editar usuario"}

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "editor": self.request.user, "negocio": self.request.negocio}

    def form_valid(self, form):
        respuesta = super().form_valid(form)
        auditar(self.request.negocio, self.request.user, "editar_usuario", self.object,
                cambios=form.changed_data)
        messages.success(self.request, "Cambios guardados.")
        return respuesta


# ---------------------------------------------------------------- cambio rápido de usuario (equipo compartido)
INTENTOS_PIN_MAX = 5


def _clave_pin(usuario_id):
    return f"pin-intentos:{usuario_id}"


def candidatos_pin(negocio):
    """Usuarios a los que se puede cambiar con PIN: activos, del mismo negocio, con PIN y que no sean administradores."""
    return (Usuario.objects.filter(negocio=negocio, is_active=True).exclude(pin="")
            .exclude(rol=Rol.ADMIN).exclude(is_superuser=True).order_by("first_name", "username"))


@login_required
def cambiar_usuario(request):
    negocio = getattr(request, "negocio", None) or request.user.negocio
    if negocio is None:
        return redirect("dashboard:inicio")
    usuarios = candidatos_pin(negocio)
    error = ""
    if request.method == "POST":
        destino = usuarios.filter(pk=request.POST.get("usuario") or 0).first()
        if destino is None:
            error = "Elige una persona de la lista."
        else:
            clave = _clave_pin(destino.pk)
            intentos = cache.get(clave, 0)
            if intentos >= INTENTOS_PIN_MAX:
                error = (f"Demasiados intentos con el PIN de {destino.get_full_name() or destino.username}. "
                         f"Espera {settings.BLOQUEO_LOGIN_MINUTOS} minutos o entra con la contraseña.")
            elif destino.verificar_pin(request.POST.get("pin", "")):
                cache.delete(clave)
                anterior = request.user
                login(request, destino, backend="django.contrib.auth.backends.ModelBackend")
                auditar(negocio, destino, "cambio_usuario_pin", destino, desde=anterior.username)
                messages.success(request, f"Hola, {destino.first_name or destino.username}. Ahora las ventas quedan a tu nombre.")
                return redirect("ventas:pos" if destino.puede("registrar_venta") else "dashboard:inicio")
            else:
                cache.set(clave, intentos + 1, settings.BLOQUEO_LOGIN_MINUTOS * 60)
                error = "PIN incorrecto."
    return render(request, "usuarios/cambiar.html", {"usuarios": usuarios, "error": error})
