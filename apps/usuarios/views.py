"""Gestión de usuarios del negocio (solo administradores)."""

from django.contrib import messages
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView

from apps.core.auditoria import auditar
from apps.core.limites import LimiteDelPlan, verificar_usuarios
from apps.core.negocio import NegocioRequeridoMixin

from .forms import UsuarioCrearForm, UsuarioEditarForm
from .models import Usuario


class UsuarioListaView(NegocioRequeridoMixin, ListView):
    model = Usuario
    permiso_requerido = "gestionar_usuarios"
    template_name = "usuarios/lista.html"
    context_object_name = "usuarios"
    ordering = ["-is_active", "first_name", "username"]


class UsuarioCrearView(NegocioRequeridoMixin, CreateView):
    model = Usuario
    form_class = UsuarioCrearForm
    permiso_requerido = "gestionar_usuarios"
    template_name = "usuarios/formulario.html"
    success_url = reverse_lazy("usuarios:lista")
    extra_context = {"titulo": "Nuevo usuario"}

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
        return {**super().get_form_kwargs(), "editor": self.request.user}

    def form_valid(self, form):
        respuesta = super().form_valid(form)
        auditar(self.request.negocio, self.request.user, "editar_usuario", self.object,
                cambios=form.changed_data)
        messages.success(self.request, "Cambios guardados.")
        return respuesta
