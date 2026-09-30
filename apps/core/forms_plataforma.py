"""Formularios del administrador de la plataforma: plan a la medida y alta de negocios."""

import secrets
import string

from django import forms
from django.conf import settings

from apps.usuarios.models import Usuario

from .models import Giro, Suscripcion
from .modulos import MODULOS

TRES = [("", "Lo del plan base"), ("1", "Sí"), ("0", "No")]


def _tres(valor):
    return None if valor in ("", None) else valor == "1"


class PlanNegocioForm(forms.Form):
    """Todo lo que se puede ajustar del plan de un negocio."""

    plan = forms.ChoiceField(label="Plan base", choices=[(k, v["nombre"]) for k, v in settings.PLANES.items()])
    pagado_hasta = forms.DateField(label="Activo hasta", required=False, widget=forms.DateInput(attrs={"type": "date"}),
                                   help_text="Para planes de pago. Vacío en Gratis.")
    prueba_hasta = forms.DateField(label="Prueba con todo hasta", required=False,
                                   widget=forms.DateInput(attrs={"type": "date"}), help_text="Vacío = sin prueba")
    limite_productos = forms.IntegerField(label="Productos", required=False, min_value=1,
                                          help_text="Vacío = lo del plan base")
    limite_usuarios = forms.IntegerField(label="Usuarios", required=False, min_value=1,
                                         help_text="Vacío = lo del plan base")
    reportes_pdf = forms.ChoiceField(label="Reportes en Excel y PDF", choices=TRES, required=False)
    api = forms.ChoiceField(label="API (conectar otros sistemas)", choices=TRES, required=False)
    modulos = forms.MultipleChoiceField(label="Módulos activos", required=False, widget=forms.CheckboxSelectMultiple,
                                        choices=[(k, v[0]) for k, v in MODULOS.items()])
    notas = forms.CharField(label="Acuerdos y pagos", required=False, widget=forms.Textarea(attrs={"rows": 3}))

    @classmethod
    def desde(cls, s: Suscripcion, data=None):
        inicial = {
            "plan": s.plan, "pagado_hasta": s.pagado_hasta, "prueba_hasta": s.prueba_hasta,
            "limite_productos": s.limite_productos, "limite_usuarios": s.limite_usuarios,
            "reportes_pdf": "" if s.reportes_pdf is None else ("1" if s.reportes_pdf else "0"),
            "api": "" if s.api is None else ("1" if s.api else "0"),
            "modulos": [k for k in MODULOS if s.tiene_modulo(k)], "notas": s.notas,
        }
        return cls(data, initial=inicial)

    def aplicar(self, s: Suscripcion) -> Suscripcion:
        d = self.cleaned_data
        s.plan, s.pagado_hasta, s.prueba_hasta = d["plan"], d["pagado_hasta"], d["prueba_hasta"]
        s.limite_productos, s.limite_usuarios = d["limite_productos"], d["limite_usuarios"]
        s.reportes_pdf, s.api = _tres(d["reportes_pdf"]), _tres(d["api"])
        s.modulos_apagados = [k for k in MODULOS if k not in d["modulos"]]
        s.notas = d["notas"]
        s.save()
        return s


def clave_temporal() -> str:
    """Fácil de dictar por teléfono y difícil de adivinar: 3 grupos de 4 (sin letras que se confunden)."""
    alfabeto = "".join(c for c in string.ascii_lowercase + string.digits if c not in "lo01")
    return "-".join("".join(secrets.choice(alfabeto) for _ in range(4)) for _ in range(3))


class NuevoNegocioForm(forms.Form):
    nombre = forms.CharField(label="Nombre del negocio", max_length=150)
    giro = forms.ChoiceField(label="Tipo de negocio", choices=Giro.choices)
    nit = forms.CharField(label="NIT / documento", max_length=30, required=False)
    telefono = forms.CharField(label="Teléfono / WhatsApp", max_length=30, required=False)
    direccion = forms.CharField(label="Dirección", max_length=200, required=False)
    dueno = forms.CharField(label="Nombre del dueño", max_length=150)
    usuario = forms.CharField(label="Usuario para entrar", max_length=150,
                              help_text="Sin espacios, por ejemplo tienda.maria")
    correo = forms.EmailField(label="Correo del dueño", required=False)
    plan = forms.ChoiceField(label="Plan base", choices=[(k, v["nombre"]) for k, v in settings.PLANES.items()],
                             initial="EMPRENDEDOR")
    dias = forms.IntegerField(label="Días activo", min_value=1, max_value=3660, initial=30,
                              help_text="Para planes de pago")

    def clean_usuario(self):
        u = self.cleaned_data["usuario"].strip()
        if " " in u:
            raise forms.ValidationError("Sin espacios.")
        if Usuario.objects.filter(username__iexact=u).exists():
            raise forms.ValidationError("Ya existe un usuario con ese nombre.")
        return u
