"""Ingreso con límite de intentos fallidos (protege contra adivinar contraseñas)."""

from django.conf import settings
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.views import LoginView
from django.core.cache import cache
from django.forms import ValidationError


def _clave(request, username):
    ip = (request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip() or request.META.get("REMOTE_ADDR", ""))
    return f"login-intentos:{(username or '').lower()}:{ip}"


class FormularioIngreso(AuthenticationForm):
    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": "Usuario, contraseña o PIN incorrectos.",
        "bloqueado": "Demasiados intentos fallidos. Espera %(minutos)s minutos e inténtalo de nuevo.",
    }

    def clean(self):
        username = self.cleaned_data.get("username")
        clave = _clave(self.request, username)
        if cache.get(clave, 0) >= settings.INTENTOS_LOGIN_MAX:
            raise ValidationError(self.error_messages["bloqueado"], code="bloqueado",
                                  params={"minutos": settings.BLOQUEO_LOGIN_MINUTOS})
        try:
            datos = super().clean()
        except ValidationError:
            cache.set(clave, cache.get(clave, 0) + 1, settings.BLOQUEO_LOGIN_MINUTOS * 60)
            raise
        cache.delete(clave)
        return datos


COOKIE_EQUIPO = "equipo_negocio"


def negocio_del_equipo(request):
    """El negocio con el que se entró la última vez en este celular o computador (para mostrar quién trabaja ahí)."""
    from apps.core.models import Negocio

    try:
        pk = request.get_signed_cookie(COOKIE_EQUIPO, salt="equipo")
    except Exception:  # noqa: BLE001 — sin cookie o alterada
        return None
    return Negocio.objects.filter(pk=pk).first()


class Ingreso(LoginView):
    form_class = FormularioIngreso
    redirect_authenticated_user = True

    def get_context_data(self, **kwargs):
        from .models import Rol, Usuario

        ctx = super().get_context_data(**kwargs)
        n = None if self.request.GET.get("otro") else negocio_del_equipo(self.request)
        if n is not None:  # botones con los nombres de quienes trabajan aquí: tocar el nombre y escribir el PIN
            ctx["equipo"] = n
            ctx["personas"] = (Usuario.objects.filter(negocio=n, is_active=True).exclude(is_superuser=True)
                               .order_by("-rol", "first_name"))
            for u in ctx["personas"]:
                u.con_pin = bool(u.pin) and u.rol != Rol.ADMIN
        return ctx

    def form_valid(self, form):
        respuesta = super().form_valid(form)
        u = form.get_user()
        if u.negocio_id:
            respuesta.set_signed_cookie(COOKIE_EQUIPO, u.negocio_id, salt="equipo", max_age=400 * 24 * 3600,
                                        httponly=True, samesite="Lax", secure=self.request.is_secure())
        return respuesta


def enlace_equipo(request, negocio) -> str:
    """Enlace para abrir en el celular de cada persona: deja listo el ingreso con los nombres del equipo."""
    from django.core import signing
    from django.urls import reverse

    return request.build_absolute_uri(reverse("equipo", args=[signing.dumps(negocio.pk, salt="enlace-equipo")]))


def entrar_equipo(request, token):
    from django.core import signing
    from django.http import Http404
    from django.shortcuts import redirect

    from apps.core.models import Negocio

    try:
        pk = signing.loads(token, salt="enlace-equipo")
    except signing.BadSignature as e:
        raise Http404 from e
    if not Negocio.objects.filter(pk=pk).exists():
        raise Http404
    respuesta = redirect("login")
    respuesta.set_signed_cookie(COOKIE_EQUIPO, pk, salt="equipo", max_age=400 * 24 * 3600, httponly=True,
                                samesite="Lax", secure=request.is_secure())
    return respuesta
