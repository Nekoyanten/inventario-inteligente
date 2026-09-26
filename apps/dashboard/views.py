from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from .selectors import resumen_negocio


@login_required
def inicio(request):
    contexto = {"resumen": resumen_negocio(request.negocio)} if request.negocio else {}
    return render(request, "dashboard/inicio.html", contexto)
