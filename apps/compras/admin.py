from django.contrib import admin

from .models import DetalleOrdenCompra, OrdenCompra


class DetalleInline(admin.TabularInline):
    model = DetalleOrdenCompra
    extra = 0


@admin.register(OrdenCompra)
class OrdenCompraAdmin(admin.ModelAdmin):
    list_display = ("id", "proveedor", "estado", "fecha_envio", "fecha_recepcion", "dias_entrega")
    list_filter = ("estado",)
    inlines = [DetalleInline]
