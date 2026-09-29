from django.contrib import admin

from apps.core.negocio import NegocioAdminMixin

from .models import Cliente, Oferta


@admin.register(Cliente)
class ClienteAdmin(NegocioAdminMixin, admin.ModelAdmin):
    list_display = ("nombre", "telefono", "nivel", "puntos", "n_compras", "negocio")
    search_fields = ("nombre", "telefono")
    list_filter = ("nivel",)


@admin.register(Oferta)
class OfertaAdmin(NegocioAdminMixin, admin.ModelAdmin):
    list_display = ("titulo", "descuento_pct", "segmento", "desde", "hasta", "activa", "negocio")
