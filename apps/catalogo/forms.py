from decimal import Decimal

from django import forms

from apps.core.negocio import del_negocio
from apps.proveedores.models import Proveedor

from .models import AtributoPersonalizado, Categoria, Marca, Producto, UnidadMedida


class ProductoForm(forms.ModelForm):
    stock_inicial = forms.DecimalField(
        label="Stock inicial", required=False, min_value=0, decimal_places=3,
        help_text="Se registra como movimiento de inventario inicial.",
    )
    vencimiento_inicial = forms.DateField(
        label="Vencimiento del stock inicial", required=False, widget=forms.DateInput(attrs={"type": "date"})
    )

    class Meta:
        model = Producto
        fields = (
            "nombre", "sku", "codigo_barras", "categoria", "marca", "unidad", "proveedor_principal",
            "precio_compra", "precio_venta", "stock_minimo", "stock_maximo", "descripcion", "imagen", "activo",
        )
        labels = {
            "sku": "Código / SKU", "codigo_barras": "Código de barras", "proveedor_principal": "Proveedor principal",
            "precio_compra": "Precio de compra (costo)", "precio_venta": "Precio de venta",
            "stock_minimo": "Stock mínimo", "stock_maximo": "Stock máximo (opcional)", "descripcion": "Descripción",
        }
        widgets = {"descripcion": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, negocio, puede_ver_costos=True, **kwargs):
        super().__init__(*args, **kwargs)
        self.negocio = negocio
        self.fields["categoria"].queryset = del_negocio(negocio, Categoria)
        self.fields["marca"].queryset = del_negocio(negocio, Marca)
        self.fields["proveedor_principal"].queryset = del_negocio(negocio, Proveedor).filter(activo=True)
        self.fields["unidad"].queryset = UnidadMedida.objects.order_by("nombre")
        self.fields["categoria"].widget.attrs["data-atributos-url"] = "/productos/atributos/"
        if self.instance.pk:
            del self.fields["stock_inicial"]
            del self.fields["vencimiento_inicial"]
        elif not getattr(negocio.config, "usa_vencimientos", False):
            del self.fields["vencimiento_inicial"]
        if not puede_ver_costos:
            del self.fields["precio_compra"]
        # Atributos personalizados de la categoría (se envían como atributo__<id>)
        self.atributos = []
        categoria_id = self.data.get("categoria") or (self.instance.categoria_id if self.instance.pk else None)
        if categoria_id:
            for a in AtributoPersonalizado.objects.filter(categoria_id=categoria_id, categoria__negocio=negocio):
                nombre = f"atributo__{a.pk}"
                if a.tipo == a.Tipo.OPCION and a.opciones:
                    campo = forms.ChoiceField(choices=[("", "—")] + [(o, o) for o in a.opciones], required=a.obligatorio)
                elif a.tipo == a.Tipo.NUMERO:
                    campo = forms.DecimalField(required=a.obligatorio)
                else:
                    campo = forms.CharField(required=a.obligatorio, max_length=100)
                campo.label = a.nombre
                campo.initial = (self.instance.atributos or {}).get(a.nombre)
                self.fields[nombre] = campo
                self.atributos.append((a, nombre))

    def clean_sku(self):
        sku = self.cleaned_data["sku"].strip().upper()
        qs = Producto.objects.filter(negocio=self.negocio, sku=sku).exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("Ya existe un producto con ese código.")
        return sku

    def clean(self):
        datos = super().clean()
        compra, venta = datos.get("precio_compra"), datos.get("precio_venta")
        if compra is not None and venta is not None and venta and venta < compra:
            self.add_error("precio_venta", "El precio de venta es menor que el costo (venderías a pérdida).")
        return datos

    def save(self, commit=True):
        producto = super().save(commit=False)
        producto.negocio = self.negocio
        valores = {}
        for atributo, nombre in self.atributos:
            valor = self.cleaned_data.get(nombre)
            if valor not in (None, ""):
                valores[atributo.nombre] = str(valor) if isinstance(valor, Decimal) else valor
        producto.atributos = valores
        if commit:
            producto.save()
        return producto


class CategoriaForm(forms.ModelForm):
    class Meta:
        model = Categoria
        fields = ("nombre",)


class MarcaForm(forms.ModelForm):
    class Meta:
        model = Marca
        fields = ("nombre",)


class AtributoForm(forms.ModelForm):
    opciones_texto = forms.CharField(
        label="Opciones (separadas por coma)", required=False, help_text="Ej: XS, S, M, L, XL"
    )

    class Meta:
        model = AtributoPersonalizado
        fields = ("categoria", "nombre", "tipo", "obligatorio")

    def __init__(self, *args, negocio, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["categoria"].queryset = del_negocio(negocio, Categoria)

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.opciones = [o.strip() for o in self.cleaned_data.get("opciones_texto", "").split(",") if o.strip()]
        if commit:
            obj.save()
        return obj


class GenerarVariantesForm(forms.Form):
    """Crea combinaciones: Talla [S, M, L] × Color [Azul, Negro] → 6 variantes."""

    def __init__(self, *args, producto, **kwargs):
        super().__init__(*args, **kwargs)
        self.producto = producto
        atributos = AtributoPersonalizado.objects.filter(categoria=producto.categoria) if producto.categoria_id else []
        for a in atributos:
            self.fields[f"valores__{a.nombre}"] = forms.CharField(
                label=f"{a.nombre} (valores separados por coma)", required=False,
                initial=", ".join(a.opciones or []),
            )
        if not self.fields:
            self.fields["valores__Variante"] = forms.CharField(
                label="Variantes (separadas por coma)", help_text="Ej: Rojo, Azul, Verde"
            )

    def combinaciones(self):
        from itertools import product as producto_cartesiano

        ejes = []
        for nombre, valor in self.cleaned_data.items():
            valores = [v.strip() for v in (valor or "").split(",") if v.strip()]
            if valores:
                ejes.append([(nombre.split("__", 1)[1], v) for v in valores])
        return [dict(c) for c in producto_cartesiano(*ejes)] if ejes else []
