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


class NegocioForm(forms.ModelForm):
    class Meta:
        from .models import Negocio

        model = Negocio
        fields = ("nombre", "nit", "telefono", "direccion")
        labels = {"nit": "NIT / documento", "telefono": "Teléfono / WhatsApp", "direccion": "Dirección"}


class ConfiguracionForm(forms.ModelForm):
    class Meta:
        from .models import ConfiguracionNegocio

        model = ConfiguracionNegocio
        exclude = ("negocio", "alertas_silenciadas")
        labels = {
            "usa_vencimientos": "Controlar fechas de vencimiento",
            "usa_lotes": "Manejar lotes (salida FEFO)",
            "usa_variantes": "Productos con variantes (talla, color, tono…)",
            "permite_fracciones": "Vender por fracciones (kg, litros)",
            "usa_temporadas": "Manejar temporadas",
            "dias_vencimiento_rojo": "Días para alerta roja de vencimiento",
            "dias_vencimiento_amarillo": "Días para alerta amarilla de vencimiento",
            "dias_sin_movimiento": "Días sin ventas para considerar baja rotación",
            "dias_exceso": "Días de cobertura que se consideran exceso",
            "horizonte_compra_dias": "Días que debe cubrir cada pedido",
            "tiempo_entrega_defecto": "Tiempo de entrega por defecto (días)",
            "alfa_suavizado": "Sensibilidad a cambios recientes en las ventas (0.1 a 0.6)",
            "resumen_por_correo": "Enviarme por correo cada mañana las alertas críticas",
            "horizonte_automatico": "Ajustar cada pedido a cada cuánto le compro a ese proveedor",
            "permite_venta_sin_stock": "Dejar vender aunque el sistema diga que no hay (queda un ajuste para revisar)",
        }

    def clean(self):
        datos = super().clean()
        if datos.get("usa_lotes") and not datos.get("usa_vencimientos"):
            # Los lotes sin vencimiento son válidos, pero avisamos la combinación más común
            pass
        alfa = datos.get("alfa_suavizado")
        if alfa is not None and not (0.05 <= alfa <= 0.9):
            self.add_error("alfa_suavizado", "Usa un valor entre 0.05 y 0.9.")
        rojo, amarillo = datos.get("dias_vencimiento_rojo"), datos.get("dias_vencimiento_amarillo")
        if rojo is not None and amarillo is not None and rojo > amarillo:
            self.add_error("dias_vencimiento_amarillo", "Debe ser mayor o igual a los días de alerta roja.")
        return datos


class CerrarCuentaForm(forms.Form):
    confirmacion = forms.CharField(label="Escribe el nombre de tu negocio para confirmar", max_length=150)
    password = forms.CharField(label="Tu contraseña", widget=forms.PasswordInput)

    def __init__(self, *args, negocio, usuario, **kwargs):
        super().__init__(*args, **kwargs)
        self.negocio, self.usuario = negocio, usuario

    def clean_confirmacion(self):
        texto = self.cleaned_data["confirmacion"].strip()
        if texto.casefold() != self.negocio.nombre.strip().casefold():
            raise forms.ValidationError("El nombre no coincide.")
        return texto

    def clean_password(self):
        if not self.usuario.check_password(self.cleaned_data["password"]):
            raise forms.ValidationError("Contraseña incorrecta.")
        return self.cleaned_data["password"]
