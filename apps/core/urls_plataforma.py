from django.urls import path

from . import views_plataforma as v

app_name = "plataforma"
urlpatterns = [path("", v.panel, name="panel")]
