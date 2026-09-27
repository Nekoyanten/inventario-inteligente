"""Páginas públicas y de soporte: ayuda, términos, privacidad, comentarios, salud y exportación de datos."""

import io
import json
import zipfile

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core import serializers
from django.db import connection
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone

from apps.usuarios.permisos import requiere_permiso

from .auditoria import auditar
from .models import Comentario
from .negocio import negocio_requerido


def ayuda(request):
    return render(request, "publico/ayuda.html")


def terminos(request):
    return render(request, "publico/terminos.html")


def privacidad(request):
    return render(request, "publico/privacidad.html")


def salud(request):
    """Para el monitoreo del servidor: responde 200 si la base de datos contesta."""
    try:
        with connection.cursor() as c:
            c.execute("SELECT 1")
        return JsonResponse({"estado": "ok"})
    except Exception:  # pragma: no cover
        return JsonResponse({"estado": "error"}, status=503)


@login_required
def comentario(request):
    if request.method == "POST" and request.POST.get("texto", "").strip():
        calif = request.POST.get("calificacion", "")
        Comentario.objects.create(
            negocio=getattr(request, "negocio", None), usuario=request.user,
            tipo=request.POST.get("tipo") if request.POST.get("tipo") in Comentario.Tipo.values else Comentario.Tipo.IDEA,
            texto=request.POST["texto"][:2000], pagina=request.POST.get("pagina", "")[:200],
            calificacion=int(calif) if calif.isdigit() and 1 <= int(calif) <= 5 else None,
        )
        messages.success(request, "¡Gracias! Leemos todos los comentarios.")
        return redirect(request.POST.get("pagina") or "dashboard:inicio")
    return render(request, "publico/comentario.html", {"tipos": Comentario.Tipo.choices,
                                                       "pagina": request.GET.get("desde", "")})


@negocio_requerido
@requiere_permiso("configurar_negocio")
def exportar_datos(request):
    """Descarga de todos los datos del negocio (portabilidad; Ley 1581 de 2012)."""
    from apps.alertas.models import Alerta
    from apps.catalogo.models import AtributoPersonalizado, Categoria, Marca, Producto
    from apps.compras.models import DetalleOrdenCompra, OrdenCompra
    from apps.inventario.models import Lote, Movimiento
    from apps.proveedores.models import ProductoProveedor, Proveedor
    from apps.ventas.models import DetalleVenta, Venta

    from .negocio import del_negocio

    n = request.negocio
    conjuntos = {
        "categorias": del_negocio(n, Categoria), "atributos": del_negocio(n, AtributoPersonalizado),
        "marcas": del_negocio(n, Marca), "proveedores": del_negocio(n, Proveedor),
        "productos": del_negocio(n, Producto), "productos_proveedor": del_negocio(n, ProductoProveedor),
        "lotes": del_negocio(n, Lote), "movimientos": del_negocio(n, Movimiento), "ventas": del_negocio(n, Venta),
        "detalles_venta": del_negocio(n, DetalleVenta), "ordenes_compra": del_negocio(n, OrdenCompra),
        "detalles_orden": del_negocio(n, DetalleOrdenCompra), "alertas": del_negocio(n, Alerta),
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for nombre, qs in conjuntos.items():
            z.writestr(f"{nombre}.json", serializers.serialize("json", qs, indent=1))
        z.writestr("LEEME.txt", f"Exportación de {n.nombre} generada el {timezone.localtime():%Y-%m-%d %H:%M}.\n"
                                "Formato JSON de Django (se puede cargar con loaddata o leer con cualquier herramienta).\n")
        z.writestr("negocio.json", json.dumps({"nombre": n.nombre, "nit": n.nit, "giro": n.giro}, ensure_ascii=False))
    auditar(n, request.user, "exportar_datos", n)
    resp = HttpResponse(buf.getvalue(), content_type="application/zip")
    resp["Content-Disposition"] = f'attachment; filename="datos-{n.pk}-{timezone.localdate():%Y%m%d}.zip"'
    return resp
