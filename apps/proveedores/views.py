from django.contrib import messages
from django.db import IntegrityError, transaction
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from apps.analitica.services import ciclo_compra
from apps.catalogo.models import Categoria, Producto
from apps.core.auditoria import auditar
from apps.core.negocio import del_negocio, negocio_requerido, obtener_del_negocio
from apps.usuarios.permisos import requiere_permiso

from .forms import ProductoProveedorForm, ProveedorForm
from .models import ProductoProveedor, Proveedor
from .services import ErrorProveedor, desempeno, reemplazar_proveedor


@negocio_requerido
@requiere_permiso("gestionar_proveedores")
def lista(request):
    proveedores = del_negocio(request.negocio, Proveedor).order_by("-activo", "nombre")
    if request.GET.get("q"):
        proveedores = proveedores.filter(nombre__icontains=request.GET["q"])
    filas = [(p, desempeno(p)) for p in proveedores]
    return render(request, "proveedores/lista.html", {"filas": filas})


@negocio_requerido
@requiere_permiso("gestionar_proveedores")
def formulario(request, pk=None):
    proveedor = obtener_del_negocio(request.negocio, Proveedor, pk=pk) if pk else None
    form = ProveedorForm(request.POST or None, instance=proveedor)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        obj.negocio = request.negocio
        obj.save()
        auditar(request.negocio, request.user, "editar_proveedor" if pk else "crear_proveedor", obj)
        messages.success(request, "Proveedor guardado.")
        return redirect("proveedores:detalle", pk=obj.pk)
    return render(request, "proveedores/formulario.html", {"form": form, "proveedor": proveedor})


@negocio_requerido
@requiere_permiso("gestionar_proveedores")
def detalle(request, pk):
    proveedor = obtener_del_negocio(request.negocio, Proveedor, pk=pk)
    form = ProductoProveedorForm(request.POST or None, negocio=request.negocio)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        obj.proveedor = proveedor
        try:
            with transaction.atomic():
                obj.save()
        except IntegrityError:
            form.add_error("producto", "Ese producto ya está asociado a este proveedor.")
        else:
            if obj.producto.proveedor_principal_id is None:
                obj.producto.proveedor_principal = proveedor
                obj.producto.save(update_fields=["proveedor_principal"])
            messages.success(request, f"{obj.producto.nombre} asociado.")
            return redirect("proveedores:detalle", pk=pk)
    return render(request, "proveedores/detalle.html", {
        "proveedor": proveedor, "indicadores": desempeno(proveedor), "form": form,
        "ciclo": ciclo_compra(proveedor),
        "productos": proveedor.productos.select_related("producto"),
        "ordenes": proveedor.ordenes.order_by("-creado")[:10],
        "otros": del_negocio(request.negocio, Proveedor).filter(activo=True).exclude(pk=proveedor.pk),
        "categorias": del_negocio(request.negocio, Categoria).filter(
            producto__proveedor_principal=proveedor).distinct(),
        "n_principal": del_negocio(request.negocio, Producto).filter(proveedor_principal=proveedor).count(),
    })


@negocio_requerido
@requiere_permiso("gestionar_proveedores")
@require_POST
def reemplazar(request, pk):
    """Cambio de proveedor en un paso: todos sus productos (o una categoría) pasan al nuevo."""
    origen = obtener_del_negocio(request.negocio, Proveedor, pk=pk)
    destino = obtener_del_negocio(request.negocio, Proveedor, pk=request.POST.get("destino") or 0)
    categoria = None
    if request.POST.get("categoria"):
        categoria = obtener_del_negocio(request.negocio, Categoria, pk=request.POST["categoria"])
    try:
        r = reemplazar_proveedor(origen=origen, destino=destino, usuario=request.user, categoria=categoria,
                                 ordenes=request.POST.get("ordenes", "esperar"),
                                 desactivar=bool(request.POST.get("desactivar")))
    except ErrorProveedor as e:
        messages.error(request, str(e))
        return redirect("proveedores:detalle", pk=pk)
    partes = [f"{r['productos']} productos pasaron a {destino.nombre}"]
    if r["borradores_movidos"]:
        partes.append(f"{r['borradores_movidos']} órdenes sin enviar ahora son de {destino.nombre}")
    if r["ordenes_en_camino"]:
        partes.append(f"{r['ordenes_en_camino']} órdenes ya enviadas siguen esperándose de {origen.nombre}")
    if r["ordenes_canceladas"]:
        partes.append(f"{r['ordenes_canceladas']} órdenes canceladas")
    if r["desactivado"]:
        partes.append(f"{origen.nombre} quedó inactivo")
    messages.success(request, ". ".join(partes) + ".")
    return redirect("proveedores:detalle", pk=destino.pk)


@negocio_requerido
@requiere_permiso("gestionar_proveedores")
@require_POST
def quitar_producto(request, pk, pp_id):
    proveedor = obtener_del_negocio(request.negocio, Proveedor, pk=pk)
    ProductoProveedor.objects.filter(proveedor=proveedor, pk=pp_id).delete()
    return redirect("proveedores:detalle", pk=pk)
