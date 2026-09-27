"""Asistente de registro en 2 pasos: datos del negocio → tipo de negocio."""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.hashers import make_password
from django.db import transaction
from django.shortcuts import redirect, render

from apps.usuarios.models import Rol, Usuario

from .auditoria import auditar
from .forms import RegistroPaso1Form, RegistroPaso2Form
from .models import Negocio
from .plantillas import funciones_activas, opciones_giro

CLAVE_SESION = "registro_paso1"


def registro_paso1(request):
    if request.user.is_authenticated and request.user.negocio_id:
        return redirect("dashboard:inicio")
    inicial = {k: v for k, v in request.session.get(CLAVE_SESION, {}).items() if k != "password_hash"}
    form = RegistroPaso1Form(request.POST or None, initial=inicial)
    if request.method == "POST" and form.is_valid():
        datos = {k: v for k, v in form.cleaned_data.items() if not k.startswith("password")}
        # Nunca se guarda la contraseña en texto plano, ni siquiera en la sesión
        datos["password_hash"] = make_password(form.cleaned_data["password1"])
        request.session[CLAVE_SESION] = datos
        return redirect("registro:paso2")
    return render(request, "registro/paso1.html", {"form": form})


def registro_paso2(request):
    datos = request.session.get(CLAVE_SESION)
    if not datos:
        return redirect("registro:paso1")
    form = RegistroPaso2Form(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if Usuario.objects.filter(username__iexact=datos["username"]).exists():
            messages.error(request, "Ese usuario acaba de ser tomado; elige otro.")
            return redirect("registro:paso1")
        with transaction.atomic():
            negocio = Negocio.objects.create(  # la señal post_save aplica la plantilla del giro
                nombre=datos["nombre_negocio"], nit=datos["nit"], telefono=datos["telefono"],
                giro=form.cleaned_data["giro"],
            )
            usuario = Usuario(
                username=datos["username"], first_name=datos["nombre"], email=datos["email"],
                telefono=datos["telefono"], negocio=negocio, rol=Rol.ADMIN, password=datos["password_hash"],
            )
            usuario.save()
            auditar(negocio, usuario, "registrar_negocio", negocio, giro=negocio.giro)
        del request.session[CLAVE_SESION]
        login(request, usuario, backend="django.contrib.auth.backends.ModelBackend")
        from .correo import enviar

        enviar("bienvenida", f"Bienvenido a {settings.EMPRESA['nombre']}", [usuario.email],
               {"usuario": usuario, "negocio": negocio})
        return redirect("registro:listo")
    return render(request, "registro/paso2.html", {"form": form, "giros": opciones_giro(), "datos": datos})


@login_required
def registro_listo(request):
    negocio = request.negocio
    if negocio is None:
        return redirect("registro:paso1")
    return render(request, "registro/listo.html", {
        "funciones": funciones_activas(negocio.config),
        "categorias": negocio.categorias.prefetch_related("atributos"),
    })
