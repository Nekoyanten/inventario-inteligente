from django.urls import path

from . import pwa

app_name = "pwa"
urlpatterns = [
    path("manifest.webmanifest", pwa.manifest, name="manifest"),
    path("sw.js", pwa.service_worker, name="sw"),
    path("sin-conexion/", pwa.sin_conexion, name="sin_conexion"),
]
