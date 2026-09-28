from django import forms

from apps.catalogo.models import Producto
from apps.core.negocio import del_negocio

from .models import TipoMovimiento

T = TipoMovimiento
TIPOS_MANUALES = [
    ("Entradas", [(t.value, t.label) for t in (T.ENTRADA_COMPRA, T.ENTRADA_DEVOLUCION_CLIENTE, T.ENTRADA_AJUSTE)]),
    ("Salidas", [(t.value, t.label) for t in (T.SALIDA_DANADO, T.SALIDA_VENCIDO, T.SALIDA_DEVOLUCION_PROVEEDOR,
                                               T.SALIDA_CONSUMO_INTERNO, T.SALIDA_AJUSTE)]),
]


class MovimientoForm(forms.Form):
    producto = forms.ModelChoiceField(queryset=Producto.objects.none(), widget=forms.HiddenInput,
                                      error_messages={"required": "Elige un producto."})
    tipo = forms.ChoiceField(choices=TIPOS_MANUALES, label="Tipo de movimiento")
    cantidad = forms.DecimalField(min_value=0.001, decimal_places=3, label="Cantidad")
    motivo = forms.CharField(max_length=255, required=False, label="Motivo / observación",
                             help_text="Obligatorio en ajustes, dañados y devoluciones.")
    costo_unitario = forms.DecimalField(min_value=0, decimal_places=2, required=False,
                                        label="Costo unitario de compra")
    fecha_vencimiento = forms.DateField(required=False, label="Fecha de vencimiento",
                                        widget=forms.DateInput(attrs={"type": "date"}))

    def __init__(self, *args, negocio, puede_ver_costos=True, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["producto"].queryset = del_negocio(negocio, Producto).filter(activo=True, es_agrupador=False)
        if not puede_ver_costos:
            del self.fields["costo_unitario"]
        if not getattr(negocio.config, "usa_vencimientos", False):
            del self.fields["fecha_vencimiento"]


class FiltroMovimientosForm(forms.Form):
    tipo = forms.ChoiceField(choices=[("", "Todos los tipos")] + list(TipoMovimiento.choices), required=False)
    desde = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    hasta = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
