from django.contrib import admin

from apps.core.negocio import NegocioAdminMixin

from .models import Comentario, ConfiguracionNegocio, EjecucionTarea, Negocio, RegistroAuditoria, Suscripcion


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


@admin.register(Suscripcion)
class SuscripcionAdmin(admin.ModelAdmin):
    list_display = ("negocio", "plan", "prueba_hasta", "pagado_hasta")
    list_filter = ("plan",)
    search_fields = ("negocio__nombre",)


@admin.register(Comentario)
class ComentarioAdmin(admin.ModelAdmin):
    list_display = ("creado", "negocio", "usuario", "tipo", "calificacion", "atendido", "texto")
    list_filter = ("tipo", "atendido")
    list_editable = ("atendido",)


@admin.register(EjecucionTarea)
class EjecucionTareaAdmin(admin.ModelAdmin):
    list_display = ("inicio", "nombre", "ok", "duracion_s")
    list_filter = ("nombre", "ok")
