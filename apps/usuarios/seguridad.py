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
        "invalid_login": "Usuario o contraseña incorrectos.",
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


class Ingreso(LoginView):
    form_class = FormularioIngreso
    redirect_authenticated_user = True
