from django import forms
from django.contrib.auth import password_validation

from apps.usuarios.models import Usuario

from .models import Giro


class RegistroPaso1Form(forms.Form):
    """Paso 1: datos del negocio y de su administrador."""

    nombre_negocio = forms.CharField(label="Nombre del negocio", max_length=150)
    nit = forms.CharField(label="NIT o documento (opcional)", max_length=30, required=False)
    telefono = forms.CharField(label="Teléfono / WhatsApp", max_length=30, required=False)
    nombre = forms.CharField(label="Tu nombre", max_length=150)
    username = forms.CharField(label="Usuario para ingresar", max_length=150)
    email = forms.EmailField(label="Correo", required=False)
    password1 = forms.CharField(label="Contraseña", widget=forms.PasswordInput)
    password2 = forms.CharField(label="Repite la contraseña", widget=forms.PasswordInput)

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if Usuario.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("Ese usuario ya existe; elige otro.")
        return username

    def clean(self):
        datos = super().clean()
        p1, p2 = datos.get("password1"), datos.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "Las contraseñas no coinciden.")
        elif p1:
            try:
                password_validation.validate_password(
                    p1, Usuario(username=datos.get("username", ""), first_name=datos.get("nombre", ""))
                )
            except forms.ValidationError as e:
                self.add_error("password1", e)
        return datos


class RegistroPaso2Form(forms.Form):
    """Paso 2: tipo de negocio (plantilla de giro)."""

    giro = forms.ChoiceField(choices=Giro.choices, widget=forms.RadioSelect, label="¿Qué tipo de negocio tienes?")
