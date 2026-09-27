from django.contrib import messages
from django.db import IntegrityError
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from apps.core.auditoria import auditar
from apps.core.negocio import del_negocio, negocio_requerido, obtener_del_negocio
from apps.usuarios.permisos import requiere_permiso

from .forms import ProductoProveedorForm, ProveedorForm
from .models import ProductoProveedor, Proveedor
from .services import desempeno


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
        "productos": proveedor.productos.select_related("producto"),
        "ordenes": proveedor.ordenes.order_by("-creado")[:10],
    })


@negocio_requerido
@requiere_permiso("gestionar_proveedores")
@require_POST
def quitar_producto(request, pk, pp_id):
    proveedor = obtener_del_negocio(request.negocio, Proveedor, pk=pk)
    ProductoProveedor.objects.filter(proveedor=proveedor, pk=pp_id).delete()
    return redirect("proveedores:detalle", pk=pk)
