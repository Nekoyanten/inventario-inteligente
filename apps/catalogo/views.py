"""Productos, variantes y catálogos auxiliares (categorías, marcas, atributos)."""

from django.contrib import messages
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from apps.core.auditoria import auditar
from apps.core.limites import LimiteDelPlan, verificar_productos
from apps.core.negocio import del_negocio, negocio_requerido, obtener_del_negocio
from apps.inventario.services import ErrorInventario, kardex, permite_decimales
from apps.usuarios.permisos import requiere_permiso

from . import selectors
from .forms import AtributoForm, CategoriaForm, GenerarVariantesForm, MarcaForm, ProductoForm
from .models import AtributoPersonalizado, Categoria, EstadoStock, Marca, Producto
from .services import crear_producto, generar_variantes


@negocio_requerido
@requiere_permiso("consultar_productos")
def lista(request):
    qs = selectors.buscar(selectors.productos_con_estado(request.negocio), request.GET.get("q"))
    if request.GET.get("categoria"):
        qs = qs.filter(categoria_id=request.GET["categoria"])
    if request.GET.get("estado"):
        qs = qs.filter(estado=request.GET["estado"])
    activo = request.GET.get("activo", "1")
    if activo in ("0", "1"):
        qs = qs.filter(activo=activo == "1")
    orden = {"stock": "stock_actual", "nombre": "nombre", "-venta": "-precio_venta"}.get(request.GET.get("orden"), "nombre")
    pagina = Paginator(qs.order_by(orden), 30).get_page(request.GET.get("pagina"))
    return render(request, "catalogo/lista.html", {
        "pagina": pagina,
        "categorias": del_negocio(request.negocio, Categoria),
        "estados": EstadoStock.choices,
        "ver_costos": request.user.puede("ver_precios_compra"),
    })


@negocio_requerido
@requiere_permiso("consultar_productos")
def buscar_json(request):
    """Búsqueda para el punto de venta y los formularios (autocompletado)."""
    qs = selectors.buscar(selectors.productos_con_estado(request.negocio).filter(activo=True), request.GET.get("q"))
    ver_costos = request.user.puede("ver_precios_compra")
    datos = [
        {
            "id": p.pk, "nombre": p.nombre, "sku": p.sku, "codigo_barras": p.codigo_barras,
            "precio_venta": float(p.precio_venta), "stock": float(p.stock_actual), "estado": p.estado,
            "unidad": p.unidad.abreviatura if p.unidad else "und", "decimales": permite_decimales(p),
            "imagen": p.imagen.url if p.imagen else None,
            **({"costo": float(p.precio_compra)} if ver_costos else {}),
        }
        for p in qs.order_by("nombre")[:20]
    ]
    return JsonResponse({"resultados": datos})


@negocio_requerido
@requiere_permiso("gestionar_productos")
def atributos_json(request, categoria_id):
    categoria = obtener_del_negocio(request.negocio, Categoria, pk=categoria_id)
    return JsonResponse({"atributos": [
        {"id": a.pk, "nombre": a.nombre, "tipo": a.tipo, "opciones": a.opciones, "obligatorio": a.obligatorio}
        for a in categoria.atributos.all()
    ]})


@negocio_requerido
@requiere_permiso("gestionar_productos")
def crear(request):
    form = ProductoForm(request.POST or None, request.FILES or None, negocio=request.negocio,
                        puede_ver_costos=request.user.puede("ver_precios_compra"))
    if request.method == "POST" and form.is_valid():
        try:
            verificar_productos(request.negocio)
            producto = crear_producto(form, request.user, form.cleaned_data.get("stock_inicial"),
                                      form.cleaned_data.get("vencimiento_inicial"))
        except LimiteDelPlan as e:
            form.add_error(None, str(e))
        except ErrorInventario as e:
            form.add_error("stock_inicial", str(e))
        else:
            messages.success(request, f"Producto {producto.nombre} creado.")
            if "otro" in request.POST:
                return redirect("catalogo:crear")
            return redirect("catalogo:detalle", pk=producto.pk)
    return render(request, "catalogo/formulario.html", {"form": form, "titulo": "Nuevo producto"})


@negocio_requerido
@requiere_permiso("gestionar_productos")
def editar(request, pk):
    producto = obtener_del_negocio(request.negocio, Producto, pk=pk)
    form = ProductoForm(request.POST or None, request.FILES or None, instance=producto, negocio=request.negocio,
                        puede_ver_costos=request.user.puede("ver_precios_compra"))
    if request.method == "POST" and form.is_valid():
        form.save()
        auditar(request.negocio, request.user, "editar_producto", producto, cambios=form.changed_data)
        messages.success(request, "Cambios guardados.")
        return redirect("catalogo:detalle", pk=producto.pk)
    contexto = {"form": form, "titulo": f"Editar {producto.nombre}", "producto": producto}
    return render(request, "catalogo/formulario.html", contexto)


@negocio_requerido
@requiere_permiso("consultar_productos")
def detalle(request, pk):
    producto = obtener_del_negocio(request.negocio, Producto.objects.select_related("categoria", "marca", "unidad",
                                   "proveedor_principal", "padre"), pk=pk)
    contexto = {"producto": producto, "ver_costos": request.user.puede("ver_precios_compra")}
    if producto.es_agrupador:
        contexto["variantes"] = producto.variantes.order_by("nombre")
    else:
        from apps.analitica.services import analizar_producto, pronostico_mensual, ventas_mensuales

        contexto["analisis"] = analizar_producto(producto)
        contexto["pronostico"] = pronostico_mensual(producto)
        contexto["ventas_mensuales"] = ventas_mensuales(producto)
        contexto["movimientos"] = kardex(producto).order_by("-fecha", "-id")[:8]
        contexto["lotes"] = producto.lotes.filter(cantidad__gt=0)
        contexto["alertas"] = producto.alertas.filter(estado__in=["ABIERTA", "VISTA"])
    return render(request, "catalogo/detalle.html", contexto)


@negocio_requerido
@requiere_permiso("gestionar_productos")
@require_POST
def cambiar_estado(request, pk):
    producto = obtener_del_negocio(request.negocio, Producto, pk=pk)
    producto.activo = not producto.activo
    producto.save(update_fields=["activo"])
    auditar(request.negocio, request.user, "activar_producto" if producto.activo else "desactivar_producto", producto)
    messages.success(request, f"{producto.nombre} {'activado' if producto.activo else 'desactivado'}.")
    return redirect("catalogo:detalle", pk=pk)


@negocio_requerido
@requiere_permiso("gestionar_productos")
def variantes(request, pk):
    producto = obtener_del_negocio(request.negocio, Producto, pk=pk)
    form = GenerarVariantesForm(request.POST or None, producto=producto)
    if request.method == "POST" and form.is_valid():
        combos = form.combinaciones()
        if not combos:
            form.add_error(None, "Escribe al menos un valor.")
        else:
            try:
                verificar_productos(request.negocio, len(combos))
                creadas = generar_variantes(producto, combos, request.user)
            except (ValueError, LimiteDelPlan) as e:
                form.add_error(None, str(e))
            else:
                messages.success(request, f"Se crearon {len(creadas)} variantes.")
                return redirect("catalogo:detalle", pk=pk)
    return render(request, "catalogo/variantes.html", {"form": form, "producto": producto})


@negocio_requerido
@requiere_permiso("gestionar_productos")
def catalogos(request):
    """Una sola pantalla para categorías, marcas y atributos personalizados."""
    negocio = request.negocio
    forms_ = {
        "categoria": CategoriaForm(prefix="cat"),
        "marca": MarcaForm(prefix="mar"),
        "atributo": AtributoForm(prefix="atr", negocio=negocio),
    }
    if request.method == "POST":
        tipo = request.POST.get("tipo")
        if tipo == "categoria":
            form = forms_["categoria"] = CategoriaForm(request.POST, prefix="cat")
        elif tipo == "marca":
            form = forms_["marca"] = MarcaForm(request.POST, prefix="mar")
        elif tipo == "atributo":
            form = forms_["atributo"] = AtributoForm(request.POST, prefix="atr", negocio=negocio)
        else:
            form = None
        if form is not None and form.is_valid():
            obj = form.save(commit=False)
            if hasattr(obj, "negocio_id"):
                obj.negocio = negocio
            try:
                with transaction.atomic():  # si el nombre ya existe, se revierte solo este intento
                    obj.save()
            except IntegrityError:
                form.add_error("nombre", "Ya existe con ese nombre.")
            else:
                messages.success(request, f"{obj} agregado.")
                return redirect("catalogo:catalogos")
    return render(request, "catalogo/catalogos.html", {
        **{f"form_{k}": v for k, v in forms_.items()},
        "categorias": del_negocio(negocio, Categoria).prefetch_related("atributos"),
        "marcas": del_negocio(negocio, Marca).order_by("nombre"),
    })


@negocio_requerido
@requiere_permiso("gestionar_productos")
@require_POST
def eliminar_catalogo(request, tipo, pk):
    modelo = {"categoria": Categoria, "marca": Marca, "atributo": AtributoPersonalizado}.get(tipo)
    if modelo is None:
        return redirect("catalogo:catalogos")
    obj = obtener_del_negocio(request.negocio, modelo, pk=pk)
    obj.delete()  # productos quedan sin categoría/marca (SET_NULL)
    messages.success(request, "Eliminado.")
    return redirect("catalogo:catalogos")
