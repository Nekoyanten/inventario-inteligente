"""Órdenes de compra: crear, enviar (PDF / WhatsApp), confirmar, recibir; y compras directas."""

from decimal import Decimal, InvalidOperation
from urllib.parse import quote

from django.contrib import messages
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from apps.core.negocio import del_negocio, negocio_requerido, obtener_del_negocio
from apps.inventario.services import ErrorInventario
from apps.proveedores.models import Proveedor
from apps.usuarios.permisos import requiere_permiso

from . import services as s
from .models import OrdenCompra


@negocio_requerido
@requiere_permiso("gestionar_compras")
def lista(request):
    qs = del_negocio(request.negocio, OrdenCompra).select_related("proveedor")
    if request.GET.get("estado"):
        qs = qs.filter(estado=request.GET["estado"])
    if request.GET.get("proveedor"):
        qs = qs.filter(proveedor_id=request.GET["proveedor"])
    pagina = Paginator(qs, 30).get_page(request.GET.get("pagina"))
    return render(request, "compras/lista.html", {
        "pagina": pagina, "estados": OrdenCompra.Estado.choices,
        "proveedores": del_negocio(request.negocio, Proveedor).filter(activo=True),
    })


def _form_lineas(request, plantilla, directa):
    proveedores = del_negocio(request.negocio, Proveedor).filter(activo=True)
    contexto = {"proveedores": proveedores, "directa": directa,
                "ver_vencimiento": getattr(request.negocio.config, "usa_vencimientos", False) and directa,
                "proveedor_id": request.POST.get("proveedor") or request.GET.get("proveedor", "")}
    if request.method == "POST":
        try:
            proveedor = proveedores.get(pk=request.POST.get("proveedor"))
            lineas = s._lineas_desde_post(request.POST, request.negocio)
            if directa:
                orden = s.registrar_compra_directa(negocio=request.negocio, proveedor=proveedor, usuario=request.user,
                                                   lineas=lineas, numero_factura=request.POST.get("numero_factura", ""))
                messages.success(request, f"Compra registrada: {len(lineas)} productos ingresaron al inventario.")
            else:
                orden = s.crear_orden(negocio=request.negocio, proveedor=proveedor, usuario=request.user, lineas=lineas,
                                      observaciones=request.POST.get("observaciones", ""),
                                      fecha_esperada=request.POST.get("fecha_esperada") or None)
                messages.success(request, f"Orden #{orden.pk} creada en borrador.")
            return redirect("compras:detalle", pk=orden.pk)
        except Proveedor.DoesNotExist:
            messages.error(request, "Elige un proveedor.")
        except ErrorInventario as e:
            messages.error(request, str(e))
    return render(request, plantilla, contexto)


@negocio_requerido
@requiere_permiso("gestionar_compras")
def crear(request):
    return _form_lineas(request, "compras/formulario.html", directa=False)


@negocio_requerido
@requiere_permiso("gestionar_compras")
def compra_directa(request):
    return _form_lineas(request, "compras/formulario.html", directa=True)


@negocio_requerido
@requiere_permiso("gestionar_compras")
def detalle(request, pk):
    orden = obtener_del_negocio(request.negocio, OrdenCompra.objects.select_related("proveedor"), pk=pk)
    detalles = orden.detalles.select_related("producto")
    whatsapp = None
    if orden.proveedor.whatsapp:
        whatsapp = f"https://wa.me/{orden.proveedor.whatsapp}?text={quote(s.mensaje_whatsapp(orden))}"
    return render(request, "compras/detalle.html", {
        "orden": orden, "detalles": detalles, "whatsapp": whatsapp,
        "puede_recibir": orden.estado in (OrdenCompra.Estado.ENVIADA, OrdenCompra.Estado.CONFIRMADA,
                                          OrdenCompra.Estado.RECIBIDA_PARCIAL),
        "ver_vencimiento": getattr(request.negocio.config, "usa_vencimientos", False),
    })


@negocio_requerido
@requiere_permiso("gestionar_compras")
@require_POST
def accion(request, pk, accion):
    orden = obtener_del_negocio(request.negocio, OrdenCompra, pk=pk)
    try:
        if accion == "enviar":
            s.enviar_orden(orden, request.user)
            messages.success(request, "Orden marcada como enviada. Descarga el PDF o envíala por WhatsApp.")
        elif accion == "confirmar":
            s.confirmar_orden(orden, request.user)
            messages.success(request, "El proveedor confirmó la orden.")
        elif accion == "cancelar":
            s.cancelar_orden(orden, request.user, request.POST.get("motivo", ""))
            messages.success(request, "Orden cancelada.")
        elif accion == "recibir":
            recibido, vencimientos = {}, {}
            for d in orden.detalles.all():
                try:
                    cant = Decimal(request.POST.get(f"recibido-{d.pk}") or "0")
                except InvalidOperation:
                    cant = Decimal("0")
                if cant > 0:
                    recibido[d.pk] = cant
                if request.POST.get(f"vencimiento-{d.pk}"):
                    vencimientos[d.pk] = s._fecha(request.POST[f"vencimiento-{d.pk}"])
            if not recibido:
                raise ErrorInventario("Indica cuánto llegó de al menos un producto.")
            s.recibir_orden(orden, request.user, recibido, request.POST.get("numero_factura", ""), vencimientos)
            messages.success(request, "Mercancía ingresada al inventario.")
    except ErrorInventario as e:
        messages.error(request, str(e))
    return redirect("compras:detalle", pk=pk)


@negocio_requerido
@requiere_permiso("gestionar_compras")
def pdf(request, pk):
    orden = obtener_del_negocio(request.negocio, OrdenCompra, pk=pk)
    resp = HttpResponse(s.pdf_orden(orden), content_type="application/pdf")
    resp["Content-Disposition"] = f'inline; filename="orden-{orden.pk}.pdf"'
    return resp
