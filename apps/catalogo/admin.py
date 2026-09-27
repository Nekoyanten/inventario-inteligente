from django.contrib import admin

from apps.core.negocio import NegocioAdminMixin

from .models import AtributoPersonalizado, Categoria, Marca, Producto, UnidadMedida


class AtributoInline(admin.TabularInline):
    model = AtributoPersonalizado
    extra = 0


@admin.register(Categoria)
class CategoriaAdmin(NegocioAdminMixin, admin.ModelAdmin):
    list_display = ("nombre", "negocio")
    inlines = [AtributoInline]


@admin.register(Producto)
class ProductoAdmin(NegocioAdminMixin, admin.ModelAdmin):
    list_display = ("sku", "nombre", "categoria", "stock_actual", "stock_minimo", "precio_venta", "activo")
    list_filter = ("activo", "categoria")
    search_fields = ("sku", "nombre", "codigo_barras")
    readonly_fields = ("stock_actual",)


admin.site.register(Marca)
admin.site.register(UnidadMedida)
