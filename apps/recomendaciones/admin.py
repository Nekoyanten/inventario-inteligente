from django.contrib import admin

from .models import RecomendacionCompra


@admin.register(RecomendacionCompra)
class RecomendacionCompraAdmin(admin.ModelAdmin):
    list_display = ("creado", "producto", "cantidad_sugerida", "proveedor", "estado")
    list_filter = ("estado",)
