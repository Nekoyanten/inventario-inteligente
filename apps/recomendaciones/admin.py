from django.contrib import admin

from apps.core.negocio import NegocioAdminMixin

from .models import RecomendacionCompra


@admin.register(RecomendacionCompra)
class RecomendacionCompraAdmin(NegocioAdminMixin, admin.ModelAdmin):
    list_display = ("creado", "producto", "cantidad_sugerida", "proveedor", "estado")
    list_filter = ("estado",)
