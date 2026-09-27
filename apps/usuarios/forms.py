from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import Usuario

ETIQUETAS = {
    "username": "Usuario", "first_name": "Nombre", "last_name": "Apellido",
    "email": "Correo", "telefono": "Teléfono", "is_active": "Activo",
}


class UsuarioCrearForm(UserCreationForm):
    class Meta:
        model = Usuario
        fields = ("username", "first_name", "last_name", "email", "telefono", "rol")
        labels = ETIQUETAS


class UsuarioEditarForm(forms.ModelForm):
    class Meta:
        model = Usuario
        fields = ("first_name", "last_name", "email", "telefono", "rol", "is_active")
        labels = ETIQUETAS

    def __init__(self, *args, editor=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.editor = editor

    def clean(self):
        datos = super().clean()
        # Evita que el administrador se bloquee a sí mismo
        if self.editor and self.instance.pk == self.editor.pk:
            if not datos.get("is_active"):
                raise forms.ValidationError("No puedes desactivar tu propio usuario.")
            if datos.get("rol") != self.instance.rol:
                raise forms.ValidationError("No puedes cambiar tu propio rol.")
        return datos
