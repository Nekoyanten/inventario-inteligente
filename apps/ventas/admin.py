from django.contrib import admin

from .models import DetalleVenta, Venta


class DetalleVentaInline(admin.TabularInline):
    model = DetalleVenta
    extra = 0


@admin.register(Venta)
class VentaAdmin(admin.ModelAdmin):
    list_display = ("id", "fecha", "vendedor", "total", "medio_pago", "estado")
    list_filter = ("estado", "medio_pago")
    inlines = [DetalleVentaInline]
