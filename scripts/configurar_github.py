"""Crea el repositorio en GitHub y carga el backlog (etiquetas, hitos, issues y tablero Project).

Requisitos: git y GitHub CLI (https://cli.github.com) con sesión iniciada:
    gh auth login
    gh auth refresh -s project        # permiso para crear el tablero

Uso (desde la raíz del proyecto):
    python scripts/configurar_github.py                       # crea Nekoyanten/inventario-inteligente privado
    python scripts/configurar_github.py --repo usuario/nombre --publico
    python scripts/configurar_github.py --sin-tablero

Es idempotente: si lo ejecutas dos veces no duplica etiquetas, hitos ni issues.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
BACKLOG = json.loads((RAIZ / "docs" / "backlog.json").read_text(encoding="utf-8"))


def gh(*args, capturar=True, permitir_error=False):
    r = subprocess.run(["gh", *args], cwd=RAIZ, capture_output=capturar, text=True, encoding="utf-8")
    if r.returncode != 0 and not permitir_error:
        print(f"✗ gh {' '.join(args[:3])}…\n{r.stderr}", file=sys.stderr)
        sys.exit(1)
    return r


def git(*args):
    return subprocess.run(["git", *args], cwd=RAIZ, capture_output=True, text=True)


def asegurar_repo(repo, privado):
    if not (RAIZ / ".git").exists():
        git("init", "-b", "main")
    if git("rev-parse", "HEAD").returncode != 0:
        git("add", "-A")
        git("commit", "-m", "Estructura inicial del sistema de inventario inteligente")
    existe = gh("repo", "view", repo, permitir_error=True).returncode == 0
    if not existe:
        print(f"→ Creando repositorio {repo}…")
        gh("repo", "create", repo, "--private" if privado else "--public", "--source", ".", "--remote", "origin",
           "--description", "Sistema de inventarios inteligente y adaptativo para pequeños emprendedores", capturar=False)
    elif git("remote", "get-url", "origin").returncode != 0:
        git("remote", "add", "origin", f"https://github.com/{repo}.git")
    print("→ Subiendo código…")
    subprocess.run(["git", "push", "-u", "origin", "main"], cwd=RAIZ, check=True)


def crear_etiquetas(repo):
    print(f"→ Etiquetas ({len(BACKLOG['etiquetas'])})")
    for e in BACKLOG["etiquetas"]:
        gh("label", "create", e["nombre"], "--color", e["color"], "--description", e["descripcion"], "--force",
           "-R", repo)


def crear_hitos(repo):
    existentes = {m["title"] for m in json.loads(gh("api", f"repos/{repo}/milestones?state=all&per_page=100").stdout)}
    print(f"→ Hitos ({len(BACKLOG['hitos'])})")
    for h in BACKLOG["hitos"]:
        if h["titulo"] not in existentes:
            gh("api", f"repos/{repo}/milestones", "-f", f"title={h['titulo']}", "-f", f"description={h['descripcion']}")


def crear_issues(repo):
    existentes = {i["title"]: i["url"] for i in json.loads(
        gh("issue", "list", "-R", repo, "--state", "all", "--limit", "500", "--json", "title,url").stdout)}
    urls = []
    print(f"→ Issues ({len(BACKLOG['issues'])})")
    for i in BACKLOG["issues"]:
        if i["titulo"] in existentes:
            urls.append(existentes[i["titulo"]])
            continue
        args = ["issue", "create", "-R", repo, "--title", i["titulo"], "--body", i["cuerpo"], "--milestone", i["hito"]]
        for etiqueta in i["etiquetas"]:
            args += ["--label", etiqueta]
        url = gh(*args).stdout.strip()
        print(f"   ✓ {url}")
        urls.append(url)
    return urls


def crear_tablero(repo, urls):
    dueno = repo.split("/")[0]
    titulo = "Inventario Inteligente — Tablero"
    proyectos = json.loads(gh("project", "list", "--owner", dueno, "--format", "json").stdout)["projects"]
    proyecto = next((p for p in proyectos if p["title"] == titulo), None)
    if not proyecto:
        proyecto = json.loads(gh("project", "create", "--owner", dueno, "--title", titulo, "--format", "json").stdout)
    numero = str(proyecto["number"])
    gh("project", "link", numero, "--owner", dueno, "--repo", repo, permitir_error=True)
    print(f"→ Agregando {len(urls)} issues al tablero #{numero}…")
    for url in urls:
        gh("project", "item-add", numero, "--owner", dueno, "--url", url, permitir_error=True)
    print(f"   Tablero: {proyecto.get('url', '')}")
    print("   Sugerencia: en el tablero crea una vista 'Board' agrupada por Status y otra agrupada por Milestone.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default="Nekoyanten/inventario-inteligente")
    ap.add_argument("--publico", action="store_true")
    ap.add_argument("--sin-tablero", action="store_true")
    a = ap.parse_args()

    if subprocess.run(["gh", "auth", "status"], capture_output=True).returncode != 0:
        sys.exit("Primero inicia sesión: gh auth login  (y luego: gh auth refresh -s project)")

    asegurar_repo(a.repo, privado=not a.publico)
    crear_etiquetas(a.repo)
    crear_hitos(a.repo)
    urls = crear_issues(a.repo)
    if not a.sin_tablero:
        crear_tablero(a.repo, urls)
    print(f"\n✅ Listo: https://github.com/{a.repo}")


if __name__ == "__main__":
    main()
