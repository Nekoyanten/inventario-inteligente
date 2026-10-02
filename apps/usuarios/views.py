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
        from apps.core.limites import suscripcion

        from .permisos import AREAS, ROLES_INFO

        ctx = super().get_context_data(**kwargs)
        lim = suscripcion(self.request.negocio).limites
        activos = sum(1 for u in ctx["usuarios"] if u.is_active)
        from .seguridad import enlace_equipo

        ctx["enlace_equipo"] = enlace_equipo(self.request, self.request.negocio)
        ctx.update({"cupo": lim["usuarios"], "activos": activos, "lleno": activos >= lim["usuarios"],
                    "contacto": settings.CONTACTO_VENTAS})
        for u in ctx["usuarios"]:
            nombres = (AREAS[a][0] for a in u.areas_efectivas if a in AREAS)
            u.areas_texto = "Todo" if u.es_admin else " · ".join(nombres)
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
        except LimiteDelPlan:
            form.add_error(None, "Ya usas todos los usuarios de tu plan. Desactiva o elimina a alguien que ya no "
                                 "trabaje contigo, o pide más usuarios en Ajustes → Mi plan.")
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
    """Todas las personas activas del negocio. Con PIN entran con el PIN; el administrador, con su contraseña."""
    return (Usuario.objects.filter(negocio=negocio, is_active=True).exclude(is_superuser=True)
            .order_by("first_name", "username"))


def _clave_valida(usuario, clave: str) -> bool:
    if usuario.rol != Rol.ADMIN and usuario.verificar_pin(clave):
        return True
    return usuario.check_password(clave)


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
            elif _clave_valida(destino, request.POST.get("pin", "")):
                cache.delete(clave)
                anterior = request.user
                login(request, destino, backend="django.contrib.auth.backends.ModelBackend")
                auditar(negocio, destino, "cambio_usuario_pin", destino, desde=anterior.username)
                messages.success(request, f"Hola, {destino.first_name or destino.username}. Ahora las ventas quedan a tu nombre.")
                return redirect("ventas:pos" if destino.puede("registrar_venta") else "dashboard:inicio")
            else:
                cache.set(clave, intentos + 1, settings.BLOQUEO_LOGIN_MINUTOS * 60)
                error = "Contraseña incorrecta." if destino.rol == Rol.ADMIN or not destino.pin else "PIN incorrecto."
    for u in usuarios:
        u.con_pin = bool(u.pin) and u.rol != Rol.ADMIN
    return render(request, "usuarios/cambiar.html", {"usuarios": usuarios, "error": error})


@login_required
def eliminar_usuario(request, pk):
    """Eliminar a alguien del equipo. Si ya tiene ventas o movimientos a su nombre, se desactiva (el historial no se
    borra) y deja libre su cupo en el plan."""
    from django.core.exceptions import PermissionDenied
    from django.db import transaction
    from django.db.models.deletion import ProtectedError

    if not request.user.puede("gestionar_usuarios") or request.method != "POST":
        raise PermissionDenied
    u = Usuario.objects.filter(negocio=request.negocio, pk=pk).first()
    if u is None or u.is_superuser:
        raise PermissionDenied
    nombre = u.get_full_name() or u.username
    if u.pk == request.user.pk:
        messages.error(request, "No puedes eliminarte a ti mismo.")
        return redirect("usuarios:editar", pk=pk)
    if u.rol == Rol.ADMIN and not Usuario.objects.filter(negocio=request.negocio, rol=Rol.ADMIN, is_active=True
                                                         ).exclude(pk=u.pk).exists():
        messages.error(request, "Es el único administrador: el negocio necesita al menos uno.")
        return redirect("usuarios:editar", pk=pk)
    try:
        with transaction.atomic():
            u.delete()
        auditar(request.negocio, request.user, "eliminar_usuario", request.negocio, persona=nombre)
        messages.success(request, f"{nombre} ya no hace parte del equipo.")
    except ProtectedError:
        u.is_active = False
        u.fijar_pin(None)
        u.save(update_fields=["is_active", "pin"])
        auditar(request.negocio, request.user, "desactivar_usuario", u, persona=u.username)
        messages.success(request, f"{nombre} quedó desactivado: ya no puede entrar y no ocupa cupo. Sus ventas y "
                                  f"movimientos se conservan en el historial.")
    return redirect("usuarios:lista")
