"""Aislamiento multi-negocio (issue: 'Aislamiento multi-negocio en todas las consultas').

Regla: TODA consulta que se haga desde una vista pasa por `del_negocio()` o por
`NegocioRequeridoMixin`. Así un usuario nunca puede ver ni modificar datos de otro negocio,
aunque cambie el id en la URL.
"""

from functools import wraps

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import FieldDoesNotExist, ImproperlyConfigured, PermissionDenied
from django.shortcuts import get_object_or_404

# Ruta al negocio para modelos que no tienen FK directa a Negocio.
RUTAS_NEGOCIO = {
    "AtributoPersonalizado": "categoria__negocio",
    "ProductoProveedor": "proveedor__negocio",
    "Lote": "producto__negocio",
    "DetalleConteo": "conteo__negocio",
    "DetalleVenta": "venta__negocio",
    "DetalleOrdenCompra": "orden__negocio",
    "DemandaDiaria": "producto__negocio",
    "RecetaItem": "producto__negocio",
    "MovimientoPuntos": "cliente__negocio",
    "EnvioOferta": "oferta__negocio",
    "ItemCuenta": "cuenta__negocio",
    "Invitado": "reserva__negocio",
}


def ruta_negocio(modelo) -> str:
    nombre = modelo.__name__
    if nombre in RUTAS_NEGOCIO:
        return RUTAS_NEGOCIO[nombre]
    if nombre == "Negocio":
        return "pk"
    try:
        modelo._meta.get_field("negocio")
        return "negocio"
    except FieldDoesNotExist as exc:
        raise ImproperlyConfigured(f"{nombre} no tiene relación con Negocio; agréguelo a RUTAS_NEGOCIO.") from exc


def del_negocio(negocio, modelo_o_qs):
    """Filtra un modelo o queryset para que solo contenga datos del negocio dado."""
    if negocio is None:
        raise PermissionDenied("El usuario no pertenece a ningún negocio.")
    qs = modelo_o_qs if hasattr(modelo_o_qs, "model") else modelo_o_qs._default_manager.all()
    campo = ruta_negocio(qs.model)
    return qs.filter(**{campo: negocio.pk if campo == "pk" else negocio})


def obtener_del_negocio(negocio, modelo_o_qs, **filtros):
    """get_object_or_404 limitado al negocio: un id de otro negocio devuelve 404, no el objeto."""
    return get_object_or_404(del_negocio(negocio, modelo_o_qs), **filtros)


def negocio_requerido(vista):
    """Decorador para vistas-función: exige usuario autenticado con negocio."""

    @wraps(vista)
    def envoltura(request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login

            return redirect_to_login(request.get_full_path())
        if request.negocio is None:
            raise PermissionDenied("El usuario no pertenece a ningún negocio.")
        return vista(request, *args, **kwargs)

    return envoltura


class NegocioRequeridoMixin(LoginRequiredMixin):
    """Para vistas basadas en clases. get_queryset() queda limitado al negocio del usuario
    y, en vistas de creación, el negocio se asigna automáticamente al guardar."""

    permiso_requerido: str | None = None

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if request.negocio is None:
            raise PermissionDenied("El usuario no pertenece a ningún negocio.")
        if self.permiso_requerido and not request.user.puede(self.permiso_requerido):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return del_negocio(self.request.negocio, super().get_queryset())

    def form_valid(self, form):
        if hasattr(form.instance, "negocio_id") and not form.instance.negocio_id:
            form.instance.negocio = self.request.negocio
        return super().form_valid(form)


class NegocioAdminMixin:
    """Para el admin de Django: un usuario staff que no es superusuario solo ve su negocio."""

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return del_negocio(request.user.negocio, qs)
