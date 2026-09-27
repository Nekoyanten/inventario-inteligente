from django.http import Http404

from apps.core.negocio import negocio_requerido
from apps.usuarios.permisos import requiere_permiso

from .exportadores import a_csv, a_excel
from .reportes import REPORTES


@negocio_requerido
@requiere_permiso("ver_reportes")
def exportar(request, clave, formato):
    if clave not in REPORTES or formato not in ("csv", "xlsx"):
        raise Http404
    titulo, funcion = REPORTES[clave]
    encabezados, filas = funcion(request.negocio)
    return (a_csv if formato == "csv" else a_excel)(clave, encabezados, filas)
