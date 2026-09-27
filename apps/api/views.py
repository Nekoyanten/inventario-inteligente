"""API REST: misma lógica y permisos que la interfaz web (integraciones, app móvil, tiendas en línea)."""

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response

from apps.alertas.models import Alerta
from apps.catalogo import selectors
from apps.catalogo.models import Producto
from apps.core.negocio import del_negocio
from apps.dashboard.selectors import resumen_negocio
from apps.inventario.models import Movimiento
from apps.inventario.services import ErrorInventario, registrar_movimiento
from apps.ventas.models import Venta
from apps.ventas.services import registrar_venta

from . import serializers as s
from .permisos import PermisoPorRol


class ProductoViewSet(viewsets.ReadOnlyModelViewSet):
    """Productos del negocio. Filtros: `?q=texto`, `?estado=AGOTADO|CRITICO|BAJO|NORMAL`."""

    serializer_class = s.ProductoSerializer
    queryset = Producto.objects.none()  # para la documentación; get_queryset filtra por negocio
    permission_classes = [PermisoPorRol]
    permisos_por_metodo = {"GET": "consultar_productos"}

    def get_queryset(self):
        qs = selectors.buscar(selectors.productos_con_estado(self.request.user.negocio), self.request.query_params.get("q"))
        if self.request.query_params.get("estado"):
            qs = qs.filter(estado=self.request.query_params["estado"])
        return qs.order_by("nombre")


class MovimientoViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    """Entradas y salidas de inventario (los movimientos no se editan ni se borran)."""

    permission_classes = [PermisoPorRol]
    permisos_por_metodo = {"GET": "registrar_movimiento", "POST": "registrar_movimiento"}

    def get_serializer_class(self):
        return s.NuevoMovimientoSerializer if self.action == "create" else s.MovimientoSerializer

    def get_queryset(self):
        qs = del_negocio(self.request.user.negocio, Movimiento).select_related("producto", "usuario")
        if self.request.query_params.get("producto"):
            qs = qs.filter(producto_id=self.request.query_params["producto"])
        return qs

    def create(self, request, *args, **kwargs):
        ser = s.NuevoMovimientoSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        producto = get_object_or_404(del_negocio(request.user.negocio, Producto), pk=d.pop("producto"))
        try:
            movs = registrar_movimiento(producto=producto, usuario=request.user, **d)
        except ErrorInventario as e:
            return Response({"error": str(e)}, status=status.HTTP_409_CONFLICT)
        return Response(s.MovimientoSerializer(movs, many=True).data, status=status.HTTP_201_CREATED)


class VentaViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    queryset = Venta.objects.none()
    permission_classes = [PermisoPorRol]
    permisos_por_metodo = {"GET": "registrar_venta", "POST": "registrar_venta"}

    def get_serializer_class(self):
        return s.NuevaVentaSerializer if self.action == "create" else s.VentaSerializer

    def get_queryset(self):
        qs = del_negocio(self.request.user.negocio, Venta).prefetch_related("detalles__producto").select_related("vendedor")
        if not self.request.user.puede("ver_reportes"):
            qs = qs.filter(vendedor=self.request.user)
        return qs

    def create(self, request, *args, **kwargs):
        ser = s.NuevaVentaSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        productos = del_negocio(request.user.negocio, Producto).filter(activo=True, es_agrupador=False)
        lineas = []
        for linea in ser.validated_data["lineas"]:
            producto = productos.filter(pk=linea["producto"]).first()
            if producto is None:
                return Response({"error": f"Producto {linea['producto']} no existe."}, status=status.HTTP_400_BAD_REQUEST)
            lineas.append({"producto": producto, "cantidad": linea["cantidad"]})
        try:
            venta = registrar_venta(negocio=request.user.negocio, vendedor=request.user, lineas=lineas,
                                    medio_pago=ser.validated_data["medio_pago"], cliente=ser.validated_data["cliente"])
        except ErrorInventario as e:
            return Response({"error": str(e)}, status=status.HTTP_409_CONFLICT)
        return Response(s.VentaSerializer(venta).data, status=status.HTTP_201_CREATED)


class AlertaViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = s.AlertaSerializer
    queryset = Alerta.objects.none()
    permission_classes = [PermisoPorRol]
    permisos_por_metodo = {"GET": "ver_reportes", "POST": "ver_reportes"}

    def get_queryset(self):
        return del_negocio(self.request.user.negocio, Alerta).filter(
            estado__in=[Alerta.Estado.ABIERTA, Alerta.Estado.VISTA]).select_related("producto")

    @action(detail=True, methods=["post"])
    def resolver(self, request, pk=None):
        alerta = self.get_object()
        alerta.estado = Alerta.Estado.RESUELTA
        alerta.resuelta_por = request.user
        alerta.nota = str(request.data.get("nota", ""))[:255]
        alerta.save()
        return Response(s.AlertaSerializer(alerta).data)


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([PermisoPorRol])
def resumen(request):
    """Indicadores del panel principal."""
    if not request.user.puede("ver_reportes"):
        return Response(status=status.HTTP_403_FORBIDDEN)
    r = resumen_negocio(request.user.negocio)
    r["alertas"].pop("ultimas")
    return Response({"inventario": r["inventario"], "ventas": r["ventas"], "alertas": r["alertas"],
                     "inmovilizado": r["inmovilizado"]})
