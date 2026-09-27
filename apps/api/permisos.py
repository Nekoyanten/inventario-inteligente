from rest_framework.permissions import BasePermission


class PermisoPorRol(BasePermission):
    """Usa la misma matriz de permisos que la interfaz web.

    La vista declara `permisos_por_metodo = {"GET": "consultar_productos", "POST": "registrar_venta"}`.
    """

    def has_permission(self, request, view):
        u = request.user
        if not (u and u.is_authenticated and getattr(u, "negocio_id", None)):
            return False
        from apps.core.limites import permite

        if not permite(u.negocio, "api"):
            self.message = "Tu plan no incluye acceso a la API. Mejora al plan Negocio."
            return False
        requerido = getattr(view, "permisos_por_metodo", {}).get(request.method)
        return requerido is None or u.puede(requerido)
