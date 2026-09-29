from django import forms

from apps.catalogo.models import Categoria, Producto
from apps.core.negocio import del_negocio

from .models import ConfiguracionNocturna, Mesa, PrecioEspecial, Reserva

DIAS = [(0, "Lun"), (1, "Mar"), (2, "Mié"), (3, "Jue"), (4, "Vie"), (5, "Sáb"), (6, "Dom")]


class MesaForm(forms.ModelForm):
    class Meta:
        model = Mesa
        fields = ("nombre", "zona", "capacidad", "consumo_minimo", "activa")


class ReservaForm(forms.ModelForm):
    class Meta:
        model = Reserva
        fields = ("tipo", "nombre", "telefono", "cliente", "fecha", "hora", "personas", "mesa", "consumo_minimo",
                  "anticipo", "promotor", "notas")
        widgets = {"fecha": forms.DateInput(attrs={"type": "date"}), "hora": forms.TimeInput(attrs={"type": "time"}),
                   "notas": forms.Textarea(attrs={"rows": 2})}
        labels = {"cliente": "Cliente registrado (opcional)"}

    def __init__(self, *args, negocio, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.clientes.models import Cliente

        self.negocio = negocio
        self.fields["cliente"].queryset = Cliente.objects.filter(negocio=negocio, activo=True)
        self.fields["mesa"].queryset = Mesa.objects.filter(negocio=negocio, activa=True)

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.negocio = self.negocio
        if commit:
            obj.save()
        return obj


class PrecioEspecialForm(forms.ModelForm):
    dias = forms.TypedMultipleChoiceField(choices=DIAS, coerce=int, widget=forms.CheckboxSelectMultiple,
                                          label="Días")

    class Meta:
        model = PrecioEspecial
        fields = ("nombre", "tipo", "valor", "dias", "hora_inicio", "hora_fin", "producto", "categoria", "activa")
        widgets = {"hora_inicio": forms.TimeInput(attrs={"type": "time"}),
                   "hora_fin": forms.TimeInput(attrs={"type": "time"})}
        labels = {"producto": "Solo este producto (opcional)", "categoria": "Solo esta categoría (opcional)"}

    def __init__(self, *args, negocio, **kwargs):
        super().__init__(*args, **kwargs)
        self.negocio = negocio
        self.fields["producto"].queryset = del_negocio(negocio, Producto).filter(activo=True).exclude(tipo="INSUMO")
        self.fields["categoria"].queryset = del_negocio(negocio, Categoria)

    def clean(self):
        datos = super().clean()
        tipo, valor = datos.get("tipo"), datos.get("valor") or 0
        if tipo == PrecioEspecial.Tipo.PORCENTAJE and not (0 < valor <= 100):
            self.add_error("valor", "Usa un porcentaje entre 1 y 100.")
        if tipo == PrecioEspecial.Tipo.PRECIO_FIJO and valor <= 0:
            self.add_error("valor", "Escribe el precio.")
        if tipo == PrecioEspecial.Tipo.PRECIO_FIJO and not datos.get("producto"):
            self.add_error("producto", "El precio fijo es para un producto.")
        if datos.get("hora_inicio") and datos.get("hora_inicio") == datos.get("hora_fin"):
            self.add_error("hora_fin", "La hora final debe ser distinta de la inicial.")
        return datos

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.negocio = self.negocio
        obj.dias = sorted(self.cleaned_data["dias"])
        if commit:
            obj.save()
        return obj


class ConfiguracionNocturnaForm(forms.ModelForm):
    class Meta:
        model = ConfiguracionNocturna
        exclude = ("negocio",)
        labels = {
            "hora_corte": "Hora en que termina la noche", "aforo": "Aforo (personas; 0 = sin control)",
            "cover_valor": "Cover por persona (0 = sin cover)", "cover_consumible": "El cover se consume en bebidas",
            "cover_gratis_desde": "Entran gratis", "acompanantes_gratis": "Acompañantes que entran gratis con ellos",
            "propina_sugerida_pct": "Propina voluntaria sugerida %",
            "grupo_minimo_personas": "Un grupo es desde (personas)", "grupo_descuento_pct": "Descuento para grupos %",
            "grupo_puntos_por_asistente": "Puntos para quien organiza, por cada asistente",
            "visitas_para_bono": "Bono cada cuántas noches de visita", "puntos_bono_visita": "Puntos del bono por visitas",
            "puntos_por_referido": "Puntos por traer un cliente nuevo",
            "botella_guardada_dias": "Días que se guarda una botella",
            "exigir_mayoria_edad": "Exigir verificación de mayoría de edad al registrar clientes",
        }

    def clean_hora_corte(self):
        h = self.cleaned_data["hora_corte"]
        if h > 12:
            raise forms.ValidationError("Usa una hora entre 0 y 12 (de la madrugada).")
        return h
