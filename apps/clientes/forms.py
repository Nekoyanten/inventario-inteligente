from datetime import timedelta

from django import forms
from django.utils import timezone

from apps.catalogo.models import Categoria, Producto
from apps.core.negocio import del_negocio
from apps.core.plantillas import GIROS_NOCTURNOS, LEY_MENORES, exige_verificar_edad, solo_adultos

from .models import Cliente, Oferta
from .services import normalizar_telefono

AUTORIZACION = ("El cliente autorizó el tratamiento de sus datos personales para fines de fidelización "
                "(Ley 1581 de 2012).")


class ClienteForm(forms.ModelForm):
    class Meta:
        model = Cliente
        fields = ("nombre", "telefono", "email", "documento", "fecha_nacimiento", "notas", "referido_por",
                  "mayor_edad_verificado", "acepta_datos", "acepta_ofertas", "activo")
        widgets = {"fecha_nacimiento": forms.DateInput(attrs={"type": "date"}),
                   "telefono": forms.TextInput(attrs={"inputmode": "tel", "autocomplete": "off"}),
                   "notas": forms.Textarea(attrs={"rows": 2})}
        labels = {"acepta_datos": AUTORIZACION, "acepta_ofertas": "Acepta recibir ofertas por WhatsApp"}

    def __init__(self, *args, negocio, **kwargs):
        super().__init__(*args, **kwargs)
        self.negocio = negocio
        self.fields["acepta_datos"].required = True
        self.nocturno = negocio.giro in GIROS_NOCTURNOS
        self.adultos = solo_adultos(negocio)
        if self.nocturno:
            self.fields["referido_por"].queryset = Cliente.objects.filter(negocio=negocio, activo=True).exclude(
                pk=self.instance.pk)
            self.fields["referido_por"].label = "¿Quién lo trajo? (gana puntos con su primera compra)"
        else:
            del self.fields["referido_por"]
        if self.adultos:
            self.fields["mayor_edad_verificado"].required = exige_verificar_edad(negocio)
        else:
            del self.fields["mayor_edad_verificado"]

    def clean_fecha_nacimiento(self):
        fecha = self.cleaned_data.get("fecha_nacimiento")
        if fecha and self.adultos:
            hoy = timezone.localdate()
            edad = hoy.year - fecha.year - ((hoy.month, hoy.day) < (fecha.month, fecha.day))
            if edad < 18:
                ley = LEY_MENORES.get(self.negocio.giro, LEY_MENORES["_"])
                raise forms.ValidationError(f"Es menor de edad: no se puede registrar ni venderle ({ley})")
        return fecha

    def clean_telefono(self):
        tel = normalizar_telefono(self.cleaned_data.get("telefono", ""))
        if tel and len(tel) < 7:
            raise forms.ValidationError("Revisa el número.")
        if tel and Cliente.objects.filter(negocio=self.negocio, telefono=tel).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Ya hay un cliente con ese número.")
        return tel

    def save(self, commit=True):
        cliente = super().save(commit=False)
        cliente.negocio = self.negocio
        if cliente.acepta_datos and not cliente.fecha_autorizacion:
            cliente.fecha_autorizacion = timezone.now()
        if commit:
            cliente.save()
        return cliente


class OfertaForm(forms.ModelForm):
    class Meta:
        model = Oferta
        fields = ("titulo", "descuento_pct", "segmento", "producto", "categoria", "desde", "hasta", "mensaje", "activa")
        widgets = {"desde": forms.DateInput(attrs={"type": "date"}), "hasta": forms.DateInput(attrs={"type": "date"}),
                   "mensaje": forms.Textarea(attrs={"rows": 3})}
        labels = {"producto": "Solo este producto (opcional)", "categoria": "Solo esta categoría (opcional)",
                  "segmento": "¿Para quién?"}

    def __init__(self, *args, negocio, **kwargs):
        super().__init__(*args, **kwargs)
        self.negocio = negocio
        self.fields["producto"].queryset = del_negocio(negocio, Producto).filter(activo=True, es_agrupador=False).exclude(
            tipo="INSUMO")
        self.fields["categoria"].queryset = del_negocio(negocio, Categoria)
        if not self.instance.pk:
            hoy = timezone.localdate()
            self.initial.setdefault("desde", hoy)
            self.initial.setdefault("hasta", hoy + timedelta(days=15))

    def clean(self):
        datos = super().clean()
        pct = datos.get("descuento_pct")
        if pct is not None and not (0 < pct <= 90):
            self.add_error("descuento_pct", "Usa un descuento entre 1 y 90 %.")
        if datos.get("desde") and datos.get("hasta") and datos["hasta"] < datos["desde"]:
            self.add_error("hasta", "La fecha final es anterior a la inicial.")
        if datos.get("producto") and datos.get("categoria"):
            self.add_error("categoria", "Elige un producto o una categoría, no ambos.")
        if datos.get("segmento") == "COMPRADORES" and not (datos.get("producto") or datos.get("categoria")):
            self.add_error("segmento", "Para «quienes han comprado» elige el producto o la categoría.")
        return datos

    def save(self, commit=True):
        oferta = super().save(commit=False)
        oferta.negocio = self.negocio
        if commit:
            oferta.save()
        return oferta


class ConfiguracionFidelizacionForm(forms.ModelForm):
    class Meta:
        from apps.core.models import ConfiguracionNegocio

        model = ConfiguracionNegocio
        fields = ("fidelizacion_activa", "pesos_por_punto", "valor_punto", "puntos_minimos_canje",
                  "nivel_frecuente_compras", "nivel_vip_monto", "encuesta_satisfaccion")
        labels = {
            "fidelizacion_activa": "Los clientes acumulan puntos",
            "pesos_por_punto": "Por cada cuántos pesos de compra se gana 1 punto",
            "valor_punto": "Cuántos pesos de descuento vale 1 punto",
            "puntos_minimos_canje": "Puntos mínimos para canjear",
            "nivel_frecuente_compras": "Compras en 90 días para ser «Frecuente»",
            "nivel_vip_monto": "Compras en pesos en 90 días para ser «VIP»",
            "encuesta_satisfaccion": "Mostrar la encuesta de satisfacción en el comprobante",
        }

    def clean(self):
        datos = super().clean()
        if datos.get("pesos_por_punto") == 0:
            self.add_error("pesos_por_punto", "Debe ser mayor que cero.")
        pp, vp = datos.get("pesos_por_punto"), datos.get("valor_punto")
        if pp and vp is not None and vp / pp > 0.2:
            self.add_error("valor_punto", f"Así devolverías el {vp / pp:.0%} de cada compra: es demasiado.")
        return datos
