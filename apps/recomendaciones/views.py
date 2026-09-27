"""Qué comprar: recomendaciones explicadas → órdenes de compra. El sistema sugiere; el empresario decide."""

from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from apps.core.negocio import del_negocio, negocio_requerido
from apps.proveedores.models import Proveedor
from apps.usuarios.permisos import requiere_permiso

from .models import RecomendacionCompra
from .services import crear_ordenes_desde_recomendaciones, descartar, generar_recomendaciones


@negocio_requerido
@requiere_permiso("gestionar_compras")
def lista(request):
    recs = (del_negocio(request.negocio, RecomendacionCompra).filter(estado=RecomendacionCompra.Estado.PENDIENTE)
            .select_related("producto", "proveedor", "producto__unidad").order_by("proveedor__nombre", "producto__nombre"))
    total = sum(r.cantidad_sugerida * r.producto.precio_compra for r in recs)
    return render(request, "recomendaciones/lista.html", {
        "recomendaciones": recs, "total": total,
        "proveedores": del_negocio(request.negocio, Proveedor).filter(activo=True),
        "ver_costos": request.user.puede("ver_precios_compra"),
    })


@negocio_requerido
@requiere_permiso("gestionar_compras")
@require_POST
def generar(request):
    recs = generar_recomendaciones(request.negocio)
    messages.success(request, f"Se calcularon {len(recs)} recomendaciones con los datos más recientes.")
    return redirect("recomendaciones:lista")


@negocio_requerido
@requiere_permiso("gestionar_compras")
@require_POST
def procesar(request):
    ids = [int(i) for i in request.POST.getlist("seleccion") if i.isdigit()]
    recs = list(del_negocio(request.negocio, RecomendacionCompra).filter(
        pk__in=ids, estado=RecomendacionCompra.Estado.PENDIENTE).select_related("producto", "proveedor"))
    if not recs:
        messages.error(request, "Selecciona al menos un producto.")
        return redirect("recomendaciones:lista")
    if request.POST.get("accion") == "descartar":
        for r in recs:
            descartar(r, request.user, request.POST.get("motivo", ""))
        messages.success(request, f"{len(recs)} recomendaciones descartadas.")
        return redirect("recomendaciones:lista")
    proveedores_negocio = {str(p.pk): p for p in del_negocio(request.negocio, Proveedor)}
    cantidades, proveedores = {}, {}
    for r in recs:
        valor = request.POST.get(f"cantidad-{r.pk}", "")
        if valor.isdigit():
            cantidades[r.pk] = int(valor)
        elegido = request.POST.get(f"proveedor-{r.pk}")
        if elegido in proveedores_negocio:
            proveedores[r.pk] = proveedores_negocio[elegido]
    ordenes = crear_ordenes_desde_recomendaciones(recs, request.user, cantidades, proveedores)
    sin_proveedor = sum(1 for r in recs if r.proveedor_id is None and r.pk not in proveedores)
    if ordenes:
        messages.success(request, f"Se crearon {len(ordenes)} órdenes en borrador (una por proveedor). Revísalas y envíalas.")
    if sin_proveedor:
        messages.warning(request, f"{sin_proveedor} productos no tienen proveedor; elige uno para incluirlos.")
    if len(ordenes) == 1:
        return redirect("compras:detalle", pk=ordenes[0].pk)
    return redirect("compras:lista") if ordenes else redirect("recomendaciones:lista")
