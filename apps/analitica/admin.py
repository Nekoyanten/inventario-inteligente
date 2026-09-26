from django.contrib import admin

from .models import DemandaDiaria


@admin.register(DemandaDiaria)
class DemandaDiariaAdmin(admin.ModelAdmin):
    list_display = ("producto", "fecha", "cantidad")
    list_filter = ("fecha",)
