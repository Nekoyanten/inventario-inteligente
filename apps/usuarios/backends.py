"""Entrar con usuario + PIN (meseros, cajeros y vendedores en el celular o el equipo del negocio).

El administrador siempre entra con su contraseña. Los intentos fallidos cuentan igual que con la contraseña."""

from django.contrib.auth.backends import ModelBackend

from .models import Rol, Usuario


class PinBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        if not username or not password or not password.isdigit() or not 4 <= len(password) <= 6:
            return None
        u = Usuario.objects.filter(username__iexact=username, is_active=True).first()
        if u is None or u.is_superuser or u.rol == Rol.ADMIN or not u.negocio_id:
            return None
        return u if u.verificar_pin(password) and self.user_can_authenticate(u) else None
