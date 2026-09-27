from django.urls import path

from . import views

app_name = "ventas"
urlpatterns = [
    path("vender/", views.pos, name="pos"),
    path("registrar/", views.registrar, name="registrar"),
    path("", views.lista, name="lista"),
    path("<int:pk>/", views.detalle, name="detalle"),
    path("<int:pk>/anular/", views.anular, name="anular"),
]
