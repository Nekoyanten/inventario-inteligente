from django.urls import path

from . import views

app_name = "recomendaciones"
urlpatterns = [
    path("", views.lista, name="lista"),
    path("generar/", views.generar, name="generar"),
    path("procesar/", views.procesar, name="procesar"),
]
