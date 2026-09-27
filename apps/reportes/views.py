from datetime import date

from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import render
from django.utils import timezone

from apps.catalogo.models import Categoria
from apps.core.negocio import del_negocio, negocio_requerido
from apps.usuarios.permisos import requiere_permiso

from .exportadores import a_csv, a_excel, a_pdf
from .reportes import REPORTES, Filtros


def _filtros(request) -> Filtros:
    def fecha(nombre):
        try:
            return date.fromisoformat(request.GET.get(nombre, ""))
        except ValueError:
            return None

    cat = request.GET.get("categoria", "")
    return Filtros(desde=fecha("desde"), hasta=fecha("hasta"), categoria=int(cat) if cat.isdigit() else None)


def _reporte(request, clave):
    if clave not in REPORTES:
        raise Http404
    titulo, descripcion, funcion, permiso, _grupo = REPORTES[clave]
    if not request.user.puede(permiso):
        raise PermissionDenied
    f = _filtros(request)
    return titulo, descripcion, funcion(request.negocio, f), f


@negocio_requerido
@requiere_permiso("ver_reportes")
def inicio(request):
    grupos: dict[str, list] = {}
    for clave, (titulo, descripcion, _f, permiso, grupo) in REPORTES.items():
        if request.user.puede(permiso):
            grupos.setdefault(grupo, []).append({"clave": clave, "titulo": titulo, "descripcion": descripcion})
    return render(request, "reportes/inicio.html", {"grupos": grupos})


@negocio_requerido
@requiere_permiso("ver_reportes")
def ver(request, clave):
    titulo, descripcion, tabla, f = _reporte(request, clave)
    return render(request, "reportes/ver.html", {
        "clave": clave, "titulo": titulo, "descripcion": descripcion, "tabla": tabla, "filtros": f,
        "filas": [list(zip(fila, tabla.tipos, strict=False)) for fila in tabla.filas[:500]],
        "totales": list(zip(tabla.totales, tabla.tipos, strict=False)) if tabla.totales else None,
        "recortado": len(tabla.filas) > 500, "categorias": del_negocio(request.negocio, Categoria),
    })


@negocio_requerido
@requiere_permiso("ver_reportes")
def exportar(request, clave, formato):
    if formato not in ("csv", "xlsx", "pdf"):
        raise Http404
    titulo, _d, tabla, f = _reporte(request, clave)
    nombre = f"{clave}-{timezone.localdate():%Y%m%d}"
    filas = tabla.filas + ([tabla.totales] if tabla.totales and formato == "csv" else [])
    if formato == "csv":
        return a_csv(nombre, tabla.encabezados, filas)
    if formato == "xlsx":
        return a_excel(nombre, tabla.encabezados, tabla.filas, tabla.tipos, tabla.totales, titulo)
    desde, hasta = f.rango()
    subtitulo = (f"{request.negocio.nombre} · generado {timezone.localtime():%d/%m/%Y %H:%M} · "
                 f"período {desde:%d/%m/%Y} – {hasta:%d/%m/%Y}")
    return a_pdf(nombre, titulo, subtitulo, tabla.encabezados, tabla.filas, tabla.tipos, tabla.totales)
