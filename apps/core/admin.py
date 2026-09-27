from django.contrib import admin

from apps.core.negocio import NegocioAdminMixin

from .models import ConfiguracionNegocio, Negocio, RegistroAuditoria


class ConfiguracionInline(admin.StackedInline):
    model = ConfiguracionNegocio
    can_delete = False


@admin.register(Negocio)
class NegocioAdmin(admin.ModelAdmin):
    list_display = ("nombre", "giro", "nit")
    inlines = [ConfiguracionInline]


@admin.register(RegistroAuditoria)
class RegistroAuditoriaAdmin(NegocioAdminMixin, admin.ModelAdmin):
    list_display = ("fecha", "usuario", "accion", "entidad", "entidad_id")
    list_filter = ("accion", "entidad")

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
