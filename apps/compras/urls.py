from django.urls import path

from . import views

app_name = "compras"
urlpatterns = [
    path("", views.lista, name="lista"),
    path("nueva/", views.crear, name="crear"),
    path("factura/", views.compra_directa, name="compra_directa"),
    path("<int:pk>/", views.detalle, name="detalle"),
    path("<int:pk>/pdf/", views.pdf, name="pdf"),
    path("<int:pk>/<str:accion>/", views.accion, name="accion"),
]
