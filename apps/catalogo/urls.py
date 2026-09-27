from django.urls import path

from . import views

app_name = "catalogo"
urlpatterns = [
    path("", views.lista, name="lista"),
    path("nuevo/", views.crear, name="crear"),
    path("buscar.json", views.buscar_json, name="buscar_json"),
    path("atributos/<int:categoria_id>/", views.atributos_json, name="atributos_json"),
    path("catalogos/", views.catalogos, name="catalogos"),
    path("catalogos/<str:tipo>/<int:pk>/eliminar/", views.eliminar_catalogo, name="eliminar_catalogo"),
    path("<int:pk>/", views.detalle, name="detalle"),
    path("<int:pk>/editar/", views.editar, name="editar"),
    path("<int:pk>/estado/", views.cambiar_estado, name="cambiar_estado"),
    path("<int:pk>/variantes/", views.variantes, name="variantes"),
]
