from django.urls import path

from . import views

app_name = "reportes"
urlpatterns = [path("<slug:clave>.<str:formato>", views.exportar, name="exportar")]
