from django.urls import path

from . import views

app_name = "usuarios"
urlpatterns = [
    path("", views.UsuarioListaView.as_view(), name="lista"),
    path("nuevo/", views.UsuarioCrearView.as_view(), name="crear"),
    path("cambiar/", views.cambiar_usuario, name="cambiar"),
    path("<int:pk>/", views.UsuarioEditarView.as_view(), name="editar"),
]
