from django.urls import path

from . import importacion, views

app_name = "reportes"
urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("importar/", importacion.importar, name="importar"),
    path("importar/plantilla.xlsx", importacion.plantilla, name="plantilla"),
    path("<slug:clave>/", views.ver, name="ver"),
    path("<slug:clave>.<str:formato>", views.exportar, name="exportar"),
]
