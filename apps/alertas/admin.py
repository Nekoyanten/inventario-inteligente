from django.contrib import admin

from apps.core.negocio import NegocioAdminMixin

from .models import Alerta


@admin.register(Alerta)
class AlertaAdmin(NegocioAdminMixin, admin.ModelAdmin):
    list_display = ("creado", "severidad", "tipo", "producto", "estado", "mensaje")
    list_filter = ("estado", "severidad", "tipo")
