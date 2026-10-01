"""Punto de venta, historial de ventas, comprobante y anulación."""

import json
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Sum
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.catalogo.models import Producto
from apps.core.negocio import del_negocio, negocio_requerido, obtener_del_negocio
from apps.core.plantillas import solo_adultos
from apps.inventario.services import ErrorInventario
from apps.usuarios.permisos import requiere_permiso

from .models import Venta
from .services import anular_venta, cantidades_inusuales, registrar_venta


@negocio_requerido
@requiere_permiso("registrar_venta")
def pos(request):
    from apps.core.modulos import activo

    config = getattr(request.negocio, "config", None)
    return render(request, "ventas/pos.html", {
        "medios": Venta.MedioPago.choices,
        "sin_stock": bool(config and config.permite_venta_sin_stock),
        "fidelizacion": bool(config and config.fidelizacion_activa) and activo(request.negocio, "clientes"),
        "puede_clientes": request.user.puede("registrar_cliente"),
        "nocturno": request.negocio.giro in ("BAR", "DISCOTECA", "BAR_DISCOTECA"),
        "solo_adultos": solo_adultos(request.negocio),
    })


def _leer_venta(request):
    """Lee el cuerpo JSON de la caja: líneas, cliente y puntos. Lanza ValueError si algo no cuadra."""
    from apps.clientes.models import Cliente

    try:
        datos = json.loads(request.body)
        lineas = []
        productos = del_negocio(request.negocio, Producto).filter(activo=True, es_agrupador=False).exclude(tipo="INSUMO")
        for linea in datos.get("lineas", []):
            cantidad = Decimal(str(linea["cantidad"]))
            if cantidad <= 0:
                continue
            lineas.append({"producto": productos.get(pk=linea["producto"]), "cantidad": cantidad})
        cliente = None
        if datos.get("cliente_id"):
            cliente = del_negocio(request.negocio, Cliente).get(pk=int(datos["cliente_id"]), activo=True)
        puntos = max(0, int(datos.get("puntos") or 0))
    except (ValueError, TypeError, KeyError, InvalidOperation, Producto.DoesNotExist, Cliente.DoesNotExist) as e:
        raise ValueError("Datos de la venta inválidos.") from e
    return datos, lineas, cliente, puntos


@negocio_requerido
@requiere_permiso("registrar_venta")
@require_POST
def cotizar(request):
    """Vista previa del cobro: ofertas que aplican, descuento por puntos y puntos que ganará."""
    from apps.clientes.services import ErrorClientes, pct_texto
    from apps.clientes.services import cotizar as cotizar_venta

    try:
        _datos, lineas, cliente, puntos = _leer_venta(request)
        c = cotizar_venta(request.negocio, lineas, cliente, puntos)
    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=400)
    except ErrorClientes as e:
        return JsonResponse({"error": str(e), "error_puntos": True}, status=400)
    return JsonResponse({
        "subtotal": float(c["subtotal"] + c["descuento_ofertas"]), "descuento_ofertas": float(c["descuento_ofertas"]),
        "descuento_puntos": float(c["descuento_puntos"]), "puntos_canjeados": c["puntos_canjeados"],
        "total": float(c["total"]), "puntos_ganados": c["puntos_ganados"],
        "ofertas": sorted({f"{linea['oferta'].titulo} (−{pct_texto(linea['pct'])} %)" for linea in c["lineas"]
                           if linea["oferta"]}),
    })


@negocio_requerido
@requiere_permiso("registrar_venta")
@require_POST
def registrar(request):
    from apps.clientes.services import ErrorClientes

    try:
        datos, lineas, cliente, puntos = _leer_venta(request)
    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=400)
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
                                cliente=str(datos.get("cliente", ""))[:120], cliente_ref=cliente, puntos_canjear=puntos)
    except (ErrorInventario, ErrorClientes) as e:
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
    venta = obtener_del_negocio(request.negocio, _ventas_visibles(request).select_related("cliente_ref"), pk=pk)
    contexto = {"venta": venta, "detalles": venta.detalles.select_related("producto", "oferta")}
    config = getattr(request.negocio, "config", None)
    if config and config.encuesta_satisfaccion and venta.estado == Venta.Estado.COMPLETADA:
        from apps.clientes.models import Encuesta
        from apps.clientes.services import url_whatsapp

        enc, _ = Encuesta.objects.get_or_create(venta=venta, defaults={"negocio": request.negocio,
                                                                       "cliente": venta.cliente_ref})
        contexto["encuesta_url"] = request.build_absolute_uri(reverse("encuesta", args=[enc.token]))
        c = venta.cliente_ref
        if c and c.telefono:
            texto = (f"¡Gracias por tu compra en {request.negocio.nombre}, {c.primer_nombre}! "
                     + (f"Ganaste {venta.puntos_ganados} puntos y ya tienes {c.puntos}. " if venta.puntos_ganados else "")
                     + f"¿Nos cuentas cómo te atendimos? {contexto['encuesta_url']}")
            contexto["whatsapp_gracias"] = url_whatsapp(c.telefono, texto)
    return render(request, "ventas/detalle.html", contexto)


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
