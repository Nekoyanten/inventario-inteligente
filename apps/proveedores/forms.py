from django import forms

from apps.catalogo.models import Producto
from apps.core.negocio import del_negocio

from .models import ProductoProveedor, Proveedor


class ProveedorForm(forms.ModelForm):
    class Meta:
        model = Proveedor
        fields = ("nombre", "nit", "contacto", "telefono", "whatsapp", "email", "tiempo_entrega_dias", "activo")
        labels = {"nit": "NIT", "telefono": "Teléfono", "whatsapp": "WhatsApp (con indicativo, ej. 573001234567)",
                  "tiempo_entrega_dias": "Tiempo de entrega prometido (días)"}


class ProductoProveedorForm(forms.ModelForm):
    class Meta:
        model = ProductoProveedor
        fields = ("producto", "precio_compra", "tiempo_entrega_dias", "multiplo_empaque", "codigo_proveedor")
        labels = {"precio_compra": "Precio de compra", "tiempo_entrega_dias": "Entrega (días, opcional)",
                  "multiplo_empaque": "Se compra de a (unidades)", "codigo_proveedor": "Código del proveedor"}

    def __init__(self, *args, negocio, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["producto"].queryset = del_negocio(negocio, Producto).filter(activo=True, es_agrupador=False)
