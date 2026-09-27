from decimal import Decimal

from rest_framework import serializers

from apps.alertas.models import Alerta
from apps.catalogo.models import Producto
from apps.inventario.forms import TIPOS_MANUALES
from apps.inventario.models import Movimiento
from apps.ventas.models import DetalleVenta, Venta


class ProductoSerializer(serializers.ModelSerializer):
    estado = serializers.SerializerMethodField()
    categoria = serializers.StringRelatedField()
    unidad = serializers.StringRelatedField()

    class Meta:
        model = Producto
        fields = ("id", "sku", "codigo_barras", "nombre", "categoria", "unidad", "precio_venta", "precio_compra",
                  "stock_actual", "stock_minimo", "estado", "activo", "atributos")

    def get_estado(self, obj):
        return obj.estado_basico()

    def to_representation(self, obj):
        datos = super().to_representation(obj)
        usuario = self.context["request"].user
        if not usuario.puede("ver_precios_compra"):
            datos.pop("precio_compra")
        return datos


class MovimientoSerializer(serializers.ModelSerializer):
    producto_nombre = serializers.CharField(source="producto.nombre", read_only=True)
    usuario = serializers.StringRelatedField()

    class Meta:
        model = Movimiento
        fields = ("id", "producto", "producto_nombre", "tipo", "cantidad", "stock_resultante", "fecha", "usuario",
                  "motivo", "marcado_anomalo")
        read_only_fields = ("stock_resultante", "fecha", "usuario", "marcado_anomalo")


class NuevoMovimientoSerializer(serializers.Serializer):
    producto = serializers.IntegerField()
    tipo = serializers.ChoiceField(choices=[c for _g, opciones in TIPOS_MANUALES for c in opciones])
    cantidad = serializers.DecimalField(max_digits=12, decimal_places=3, min_value=Decimal("0.001"))
    motivo = serializers.CharField(required=False, allow_blank=True, default="")
    costo_unitario = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)
    fecha_vencimiento = serializers.DateField(required=False)


class LineaVentaSerializer(serializers.Serializer):
    producto = serializers.IntegerField()
    cantidad = serializers.DecimalField(max_digits=12, decimal_places=3, min_value=Decimal("0.001"))


class NuevaVentaSerializer(serializers.Serializer):
    lineas = LineaVentaSerializer(many=True)
    medio_pago = serializers.ChoiceField(choices=Venta.MedioPago.choices, default=Venta.MedioPago.EFECTIVO)
    cliente = serializers.CharField(required=False, allow_blank=True, default="")


class DetalleVentaSerializer(serializers.ModelSerializer):
    producto_nombre = serializers.CharField(source="producto.nombre", read_only=True)

    class Meta:
        model = DetalleVenta
        fields = ("producto", "producto_nombre", "cantidad", "precio_unitario", "descuento")


class VentaSerializer(serializers.ModelSerializer):
    detalles = DetalleVentaSerializer(many=True, read_only=True)
    vendedor = serializers.StringRelatedField()

    class Meta:
        model = Venta
        fields = ("id", "fecha", "vendedor", "cliente", "medio_pago", "total", "estado", "detalles")


class AlertaSerializer(serializers.ModelSerializer):
    producto_nombre = serializers.CharField(source="producto.nombre", read_only=True, default=None)

    class Meta:
        model = Alerta
        fields = ("id", "tipo", "severidad", "estado", "mensaje", "accion_sugerida", "producto", "producto_nombre",
                  "creado")
