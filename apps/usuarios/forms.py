from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import Usuario

ETIQUETAS = {
    "username": "Usuario", "first_name": "Nombre", "last_name": "Apellido",
    "email": "Correo", "telefono": "Teléfono", "is_active": "Activo",
}


PIN_AYUDA = ("4 a 6 números para cambiar de usuario rápido en un celular compartido (solo vendedores y encargados; "
             "el administrador entra siempre con su contraseña).")


class PinMixin:
    def _campo_pin(self):
        self.fields["pin_nuevo"] = forms.RegexField(
            regex=r"^\d{4,6}$", required=False, label="PIN", help_text=PIN_AYUDA,
            widget=forms.PasswordInput(attrs={"inputmode": "numeric", "autocomplete": "new-password"}),
            error_messages={"invalid": "El PIN debe tener de 4 a 6 números."})

    def _guardar_pin(self, usuario):
        pin = self.cleaned_data.get("pin_nuevo")
        if self.cleaned_data.get("quitar_pin"):
            usuario.fijar_pin(None)
        elif pin:
            usuario.fijar_pin(pin)


class UsuarioCrearForm(PinMixin, UserCreationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._campo_pin()

    def save(self, commit=True):
        usuario = super().save(commit=False)
        self._guardar_pin(usuario)
        if commit:
            usuario.save()
        return usuario

    class Meta:
        model = Usuario
        fields = ("username", "first_name", "last_name", "email", "telefono", "rol")
        labels = ETIQUETAS


class UsuarioEditarForm(PinMixin, forms.ModelForm):
    quitar_pin = forms.BooleanField(required=False, label="Quitar el PIN")

    class Meta:
        model = Usuario
        fields = ("first_name", "last_name", "email", "telefono", "rol", "is_active")
        labels = ETIQUETAS

    def __init__(self, *args, editor=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.editor = editor
        self._campo_pin()
        self.fields["pin_nuevo"].help_text = ("Déjalo vacío para no cambiarlo. " +
                                              ("Ya tiene PIN. " if self.instance.pin else "") + PIN_AYUDA)

    def save(self, commit=True):
        usuario = super().save(commit=False)
        self._guardar_pin(usuario)
        if commit:
            usuario.save()
        return usuario

    def clean(self):
        datos = super().clean()
        # Evita que el administrador se bloquee a sí mismo
        if self.editor and self.instance.pk == self.editor.pk:
            if not datos.get("is_active"):
                raise forms.ValidationError("No puedes desactivar tu propio usuario.")
            if datos.get("rol") != self.instance.rol:
                raise forms.ValidationError("No puedes cambiar tu propio rol.")
        return datos
