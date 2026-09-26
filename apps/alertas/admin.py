from django.contrib import admin

from .models import Alerta


@admin.register(Alerta)
class AlertaAdmin(admin.ModelAdmin):
    list_display = ("creado", "severidad", "tipo", "producto", "estado", "mensaje")
    list_filter = ("estado", "severidad", "tipo")
