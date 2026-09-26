from django.contrib import admin

from .models import ConteoFisico, DetalleConteo, Lote, Movimiento


@admin.register(Movimiento)
class MovimientoAdmin(admin.ModelAdmin):
    list_display = ("fecha", "producto", "tipo", "cantidad", "stock_resultante", "usuario", "motivo")
    list_filter = ("tipo", "marcado_anomalo")
    search_fields = ("producto__nombre", "producto__sku", "motivo")

    def has_change_permission(self, request, obj=None):
        return False  # inmutables

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Lote)
class LoteAdmin(admin.ModelAdmin):
    list_display = ("producto", "codigo", "fecha_vencimiento", "cantidad")
    list_filter = ("fecha_vencimiento",)


class DetalleConteoInline(admin.TabularInline):
    model = DetalleConteo
    extra = 0


@admin.register(ConteoFisico)
class ConteoFisicoAdmin(admin.ModelAdmin):
    list_display = ("id", "creado", "responsable", "estado")
    inlines = [DetalleConteoInline]
