from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import Rol, Usuario
from .permisos import AREAS, areas_disponibles, areas_por_defecto

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


class AreasMixin:
    """«Qué puede ver»: casillas con las áreas; vienen marcadas las de su rol y el dueño puede cambiarlas."""

    def _campo_areas(self, negocio):
        self.negocio = negocio
        disponibles = areas_disponibles(negocio) if negocio else list(AREAS)
        self.fields["rol"].help_text = "El rol trae marcadas sus áreas; puedes cambiarlas abajo."
        self.fields["areas_elegidas"] = forms.MultipleChoiceField(
            label="Qué puede ver y hacer", required=False, widget=forms.CheckboxSelectMultiple,
            choices=[(k, f"{AREAS[k][0]} — {AREAS[k][1]}") for k in disponibles],
            help_text="Si no marcas nada, verá lo de su rol. El administrador siempre ve todo.")
        u = self.instance
        if u.pk:
            self.initial["areas_elegidas"] = [a for a in u.areas_efectivas if a in disponibles]
        else:
            rol = self.initial.get("rol") or Rol.VENDEDOR
            self.initial["areas_elegidas"] = [a for a in areas_por_defecto(rol, getattr(negocio, "giro", ""))
                                              if a in disponibles]
        self.defecto_por_rol = {r: [a for a in areas_por_defecto(r, getattr(negocio, "giro", "")) if a in disponibles]
                                for r, _ in Rol.choices}

    def _guardar_areas(self, usuario):
        elegidas = [a for a in AREAS if a in self.cleaned_data.get("areas_elegidas", [])]
        defecto = self.defecto_por_rol.get(usuario.rol, [])
        usuario.areas = None if usuario.rol == Rol.ADMIN or elegidas == defecto else elegidas

    def clean_areas_elegidas(self):
        elegidas = self.cleaned_data.get("areas_elegidas") or []
        if not elegidas:  # sin marcar nada: lo de su rol
            return self.defecto_por_rol.get(self.cleaned_data.get("rol", self.instance.rol), [])
        return elegidas


class UsuarioCrearForm(AreasMixin, PinMixin, UserCreationForm):
    def __init__(self, *args, negocio=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._campo_pin()
        self._campo_areas(negocio)
        self.fields["username"].help_text = "Con esto entra al sistema. Sin espacios, por ejemplo: ana.mesera"
        self.fields["password1"].help_text = "Mínimo 8 caracteres y que no sea solo números."
        self.fields["password2"].help_text = "Escríbela otra vez."

    def save(self, commit=True):
        usuario = super().save(commit=False)
        self._guardar_pin(usuario)
        self._guardar_areas(usuario)
        if commit:
            usuario.save()
        return usuario

    class Meta:
        model = Usuario
        fields = ("username", "first_name", "last_name", "email", "telefono", "rol")
        labels = ETIQUETAS


class UsuarioEditarForm(AreasMixin, PinMixin, forms.ModelForm):
    quitar_pin = forms.BooleanField(required=False, label="Quitar el PIN")

    class Meta:
        model = Usuario
        fields = ("first_name", "last_name", "email", "telefono", "rol", "is_active")
        labels = ETIQUETAS

    def __init__(self, *args, editor=None, negocio=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.editor = editor
        self._campo_pin()
        self._campo_areas(negocio)
        self.fields["pin_nuevo"].help_text = ("Déjalo vacío para no cambiarlo. " +
                                              ("Ya tiene PIN. " if self.instance.pin else "") + PIN_AYUDA)

    def save(self, commit=True):
        usuario = super().save(commit=False)
        self._guardar_pin(usuario)
        self._guardar_areas(usuario)
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
