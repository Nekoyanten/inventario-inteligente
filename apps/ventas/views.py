"""Punto de venta, historial de ventas, comprobante y anulación."""

import json
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Sum
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from apps.catalogo.models import Producto
from apps.core.negocio import del_negocio, negocio_requerido, obtener_del_negocio
from apps.inventario.services import ErrorInventario
from apps.usuarios.permisos import requiere_permiso

from .models import Venta
from .services import anular_venta, cantidades_inusuales, registrar_venta


@negocio_requerido
@requiere_permiso("registrar_venta")
def pos(request):
    config = getattr(request.negocio, "config", None)
    return render(request, "ventas/pos.html", {
        "medios": Venta.MedioPago.choices,
        "sin_stock": bool(config and config.permite_venta_sin_stock),
    })


@negocio_requerido
@requiere_permiso("registrar_venta")
@require_POST
def registrar(request):
    try:
        datos = json.loads(request.body)
        lineas = []
        productos = del_negocio(request.negocio, Producto).filter(activo=True, es_agrupador=False)
        for linea in datos.get("lineas", []):
            cantidad = Decimal(str(linea["cantidad"]))
            if cantidad <= 0:
                continue
            lineas.append({"producto": productos.get(pk=linea["producto"]), "cantidad": cantidad})
    except (ValueError, KeyError, InvalidOperation, Producto.DoesNotExist):
        return JsonResponse({"error": "Datos de la venta inválidos."}, status=400)
    if not lineas:
        return JsonResponse({"error": "La venta no tiene productos."}, status=400)
    medio = datos.get("medio_pago", Venta.MedioPago.EFECTIVO)
    if medio not in Venta.MedioPago.values:
        medio = Venta.MedioPago.EFECTIVO
    if not datos.get("confirmado"):
        avisos = cantidades_inusuales(lineas)
        if avisos:  # 428: el cajero confirma y se reenvía con "confirmado": true
            return JsonResponse({"confirmar": avisos}, status=428)
    try:
        venta = registrar_venta(negocio=request.negocio, vendedor=request.user, lineas=lineas, medio_pago=medio,
                                cliente=str(datos.get("cliente", ""))[:120])
    except ErrorInventario as e:
        return JsonResponse({"error": str(e)}, status=409)
    return JsonResponse({"venta": venta.pk, "total": float(venta.total)})


def _ventas_visibles(request):
    qs = del_negocio(request.negocio, Venta).select_related("vendedor")
    if not request.user.puede("ver_reportes"):
        qs = qs.filter(vendedor=request.user)  # el vendedor solo ve sus ventas
    return qs


@negocio_requerido
@requiere_permiso("registrar_venta")
def lista(request):
    qs = _ventas_visibles(request)
    if request.GET.get("desde"):
        qs = qs.filter(fecha__date__gte=request.GET["desde"])
    if request.GET.get("hasta"):
        qs = qs.filter(fecha__date__lte=request.GET["hasta"])
    if request.GET.get("medio"):
        qs = qs.filter(medio_pago=request.GET["medio"])
    resumen = qs.filter(estado=Venta.Estado.COMPLETADA).aggregate(total=Sum("total"), cantidad=Count("id"))
    pagina = Paginator(qs, 40).get_page(request.GET.get("pagina"))
    return render(request, "ventas/lista.html", {"pagina": pagina, "resumen": resumen, "medios": Venta.MedioPago.choices})


@negocio_requerido
@requiere_permiso("registrar_venta")
def detalle(request, pk):
    venta = obtener_del_negocio(request.negocio, _ventas_visibles(request), pk=pk)
    return render(request, "ventas/detalle.html", {"venta": venta, "detalles": venta.detalles.select_related("producto")})


@negocio_requerido
@requiere_permiso("configurar_negocio")
@require_POST
def anular(request, pk):
    venta = obtener_del_negocio(request.negocio, Venta, pk=pk)
    try:
        anular_venta(venta, request.user, request.POST.get("motivo", ""))
    except (ValueError, ErrorInventario) as e:
        messages.error(request, str(e))
    else:
        messages.success(request, f"Venta #{venta.pk} anulada y el inventario fue devuelto.")
    return redirect("ventas:detalle", pk=pk)
