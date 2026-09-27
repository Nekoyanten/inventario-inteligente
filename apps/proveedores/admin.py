from django.contrib import admin

from apps.core.negocio import NegocioAdminMixin

from .models import ProductoProveedor, Proveedor


class ProductoProveedorInline(admin.TabularInline):
    model = ProductoProveedor
    extra = 0
    autocomplete_fields = ("producto",)


@admin.register(Proveedor)
class ProveedorAdmin(NegocioAdminMixin, admin.ModelAdmin):
    list_display = ("nombre", "telefono", "tiempo_entrega_dias", "activo")
    search_fields = ("nombre",)
    inlines = [ProductoProveedorInline]
