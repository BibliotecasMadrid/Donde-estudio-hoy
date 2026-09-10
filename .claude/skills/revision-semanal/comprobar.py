#!/usr/bin/env python3
"""
comprobar.py - Chequeo semanal del repositorio.

Reune en un solo informe las comprobaciones que hay que repasar cada viernes, con el
foco puesto en que los horarios sigan siendo los que publica la fuente oficial. No
arregla nada ni escribe en el repositorio: solo mira y cuenta.

  python .claude/skills/revision-semanal/comprobar.py            # todo
  python .claude/skills/revision-semanal/comprobar.py --sin-red  # sin salir a internet

Codigos de salida: 0 todo correcto, 1 hay avisos, 2 hay fallos.
"""

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request

RAIZ = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
CALENDARIO = os.path.join(RAIZ, "calendario.json")
SITIO = "https://bibliotecasmadrid.es"
BIBLIOAGENDA_UAM = "https://biblioagenda.uam.es/api_hours_today.php?iid=3941&lid=0&format=json"

# Cuanto puede envejecer una verificacion antes de que deje de ser creible. Los horarios
# de Madrid cambian por temporada (verano, Navidad, Semana Santa), asi que un mes sin
# repasar la fuente ya es mucho y tres meses es una fuente caducada.
DIAS_AVISO = 35
DIAS_FALLO = 120

OK, AVISO, FALLO = "OK", "AVISO", "FALLO"
resultados = []


def anota(estado, titulo, detalle=""):
    resultados.append((estado, titulo, detalle))


def ejecutar(cmd, timeout=900):
    """Lanza un comando en la raiz del repo y devuelve (codigo, salida)."""
    proc = subprocess.run(cmd, cwd=RAIZ, capture_output=True, text=True, timeout=timeout)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def hoy():
    return dt.date.today()


def dias_desde(fecha_iso):
    return (hoy() - dt.date.fromisoformat(fecha_iso)).days


# --- 1. El calendario esta vigente ---------------------------------------------------

def revisar_calendario(cal):
    anio = int(cal["year"])
    actual = hoy().year
    if anio < actual:
        anota(FALLO, "Calendario vencido",
              f"calendario.json es de {anio} y estamos en {actual}. build.sh aborta el "
              f"despliegue: la web se queda congelada en la ultima version buena.")
    elif hoy().month == 12 and anio == actual:
        anota(AVISO, "Falta el calendario del ano que viene",
              f"quedan {(dt.date(actual, 12, 31) - hoy()).days} dias para que "
              f"calendario.json {anio} caduque y bloquee el despliegue de enero.")
    else:
        anota(OK, "Calendario vigente", f"ano {anio}, {len(cal['places'])} centros")


# --- 2. Cuando se comprobaron las fuentes oficiales por ultima vez --------------------

def revisar_frescura(cal):
    fechas = {}
    sin_fecha = []
    for slug, perfil in cal["places"].items():
        fecha = (perfil.get("source") or {}).get("checked_at")
        if fecha and re.fullmatch(r"\d{4}-\d{2}-\d{2}", fecha):
            fechas.setdefault(fecha, []).append(slug)
        else:
            sin_fecha.append(slug)

    if sin_fecha:
        anota(FALLO, "Centros sin fecha de verificacion",
              f"{len(sin_fecha)}: {', '.join(sorted(sin_fecha)[:10])}")
    if not fechas:
        return

    reciente = max(fechas)
    antigua = min(fechas)
    dias = dias_desde(reciente)
    caducados = sum(len(s) for f, s in fechas.items() if dias_desde(f) > DIAS_FALLO)
    viejos = sum(len(s) for f, s in fechas.items() if dias_desde(f) > DIAS_AVISO)
    detalle = (f"ultima verificacion {reciente} (hace {dias} dias); la mas antigua "
               f"{antigua} (hace {dias_desde(antigua)}); {viejos} centros por encima de "
               f"{DIAS_AVISO} dias")

    if caducados:
        anota(FALLO, "Horarios sin verificar desde hace demasiado",
              detalle + f"; {caducados} superan {DIAS_FALLO} dias")
    elif viejos:
        anota(AVISO, "Toca repasar fuentes oficiales", detalle)
    else:
        anota(OK, "Fuentes recien verificadas", detalle)

    ultima = cal.get("last_updated")
    if ultima and ultima != reciente:
        anota(AVISO, "last_updated no cuadra",
              f"calendario.json dice {ultima} y la verificacion mas reciente es {reciente}")


# --- 3. La auditoria: el calendario dice lo mismo que la fuente -----------------------

def revisar_auditoria():
    codigo, salida = ejecutar([sys.executable, "auditar_horarios.py", "--informe"])
    if codigo != 0:
        anota(FALLO, "auditar_horarios.py no termina", salida.strip()[-600:])
        return

    divergen = [ln[3:].strip() for ln in salida.splitlines() if ln.startswith("!! ")]
    total = re.search(r"---\s*(\d+)\s*avisos\s*---", salida)
    n_avisos = int(total.group(1)) if total else 0
    # Los avisos de solo_url son de diseno: esos perfiles no se derivan del texto.
    solo_url = salida.count("(source.solo_url)")

    if divergen:
        anota(FALLO, "El calendario no coincide con la fuente oficial",
              f"{len(divergen)} centros: {', '.join(divergen)}. "
              f"Mira su bloque '!!' en `python auditar_horarios.py --informe`: "
              f"compara 'calendario:' con 'oficial:'.")
    else:
        anota(OK, "Calendario y fuente oficial coinciden", "ningun centro marcado con '!!'")

    interpretacion = n_avisos - solo_url
    if interpretacion > 0:
        anota(AVISO, "Lineas de horario sin interpretar",
              f"{interpretacion} avisos ajenos a solo_url sobre {n_avisos} totales "
              f"({solo_url} son perfiles solo_url, esperados)")
    else:
        anota(OK, "Sin avisos de interpretacion",
              f"{n_avisos} avisos, todos de perfiles solo_url")


# --- 4. Las paginas publicadas salen de index.html ------------------------------------

def revisar_build():
    codigo, sucio = ejecutar(["git", "status", "--porcelain"])
    if codigo != 0:
        anota(FALLO, "git status falla", sucio.strip()[-400:])
        return
    if sucio.strip():
        anota(AVISO, "Arbol de trabajo con cambios sin commitear",
              "no se regenera el build para no pisarlos: " + sucio.strip()[:300])
        return

    codigo, salida = ejecutar([sys.executable, "build.py"])
    if codigo != 0:
        anota(FALLO, "build.py falla", salida.strip()[-600:])
        return

    _, diff = ejecutar(["git", "status", "--porcelain"])
    if diff.strip():
        archivos = [ln[3:] for ln in diff.strip().splitlines()]
        ejecutar(["git", "checkout", "--", "."])
        anota(FALLO, "Lo commiteado no es lo que genera build.py",
              f"{len(archivos)} archivos cambian al regenerar: "
              f"{', '.join(archivos[:8])}. Alguien edito index.html o calendario.json "
              f"sin ejecutar build.py. (Ya se han restaurado.)")
    else:
        anota(OK, "Paginas y sitemap al dia", "build.py no cambia nada de lo commiteado")


# --- 5. Los 12 meses de horarios existen ---------------------------------------------

def revisar_meses(cal):
    anio = cal["year"]
    faltan = [f"{anio}-{m:02d}.json" for m in range(1, 13)
              if not os.path.isfile(os.path.join(RAIZ, "horarios", f"{anio}-{m:02d}.json"))]
    if faltan:
        anota(FALLO, "Faltan meses de horarios",
              f"{', '.join(faltan)}. build.sh aborta el despliegue sin ellos.")
        return

    mes = os.path.join(RAIZ, "horarios", f"{anio}-{hoy().month:02d}.json")
    with open(mes, encoding="utf-8") as f:
        datos = json.load(f)
    centros = datos.get("places", datos)
    anota(OK, "Calendario mensual completo",
          f"12 archivos en horarios/; el de este mes trae {len(centros)} centros")


# --- 6. Los tests del generador -------------------------------------------------------

def revisar_tests():
    try:
        import PIL  # noqa: F401
    except ImportError:
        anota(AVISO, "Tests no ejecutados",
              "falta Pillow (lo importa fotos.py). Instalalo con `pip install pillow` "
              "y repite `python -m unittest test_build`.")
        return
    codigo, salida = ejecutar([sys.executable, "-m", "unittest", "test_build"])
    if codigo != 0:
        anota(FALLO, "test_build falla", salida.strip()[-800:])
    else:
        cuantos = re.search(r"Ran (\d+) tests?", salida)
        anota(OK, "Tests del generador en verde",
              f"{cuantos.group(1) if cuantos else '?'} tests")


# --- 7. La web publicada ---------------------------------------------------------------

def pedir(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": "DondeEstudioHoy-revision/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read()


def revisar_sitio(cal):
    try:
        estado, _ = pedir(SITIO + "/")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        anota(FALLO, "La web no responde", f"{SITIO}: {e}")
        return
    if estado != 200:
        anota(FALLO, "La web responde con error", f"{SITIO}: HTTP {estado}")
        return

    ruta_mes = f"/horarios/{cal['year']}-{hoy().month:02d}.json"
    try:
        estado, cuerpo = pedir(SITIO + ruta_mes)
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        anota(FALLO, "El calendario del mes no se sirve", f"{ruta_mes}: {e}")
        return
    if estado != 200:
        anota(FALLO, "El calendario del mes no se sirve", f"{ruta_mes}: HTTP {estado}")
        return

    local = os.path.join(RAIZ, "horarios", f"{cal['year']}-{hoy().month:02d}.json")
    with open(local, "rb") as f:
        igual = hashlib.sha256(f.read()).hexdigest() == hashlib.sha256(cuerpo).hexdigest()
    if igual:
        anota(OK, "Web publicada al dia", f"{ruta_mes} coincide con el repositorio")
    else:
        anota(AVISO, "La web sirve un calendario distinto al del repositorio",
              f"{ruta_mes} difiere: despliegue pendiente o cache de borde de Cloudflare")


def revisar_biblioagenda():
    """Las 24 fichas de UCM/UAM pintan su horario en vivo desde esta API."""
    try:
        estado, cuerpo = pedir(BIBLIOAGENDA_UAM)
        json.loads(cuerpo)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
        anota(AVISO, "BiblioAgenda (UAM/UCM) no responde",
              f"{e}. Si sigue caida, las fichas de UAM y UCM se quedan sin horario en vivo.")
        return
    if estado == 200:
        anota(OK, "BiblioAgenda (UAM/UCM) responde", "las fichas universitarias siguen en vivo")
    else:
        anota(AVISO, "BiblioAgenda (UAM/UCM) responde raro", f"HTTP {estado}")


def main():
    p = argparse.ArgumentParser(description="Chequeo semanal del repositorio")
    p.add_argument("--sin-red", action="store_true", help="omite las comprobaciones online")
    args = p.parse_args()

    with open(CALENDARIO, encoding="utf-8") as f:
        cal = json.load(f)

    revisar_calendario(cal)
    revisar_frescura(cal)
    revisar_auditoria()
    revisar_build()
    revisar_meses(cal)
    revisar_tests()
    if not args.sin_red:
        revisar_sitio(cal)
        revisar_biblioagenda()

    fallos = sum(1 for e, _, _ in resultados if e == FALLO)
    avisos = sum(1 for e, _, _ in resultados if e == AVISO)

    print(f"REVISION SEMANAL - {hoy().isoformat()}\n")
    for estado, titulo, detalle in resultados:
        print(f"[{estado:5}] {titulo}")
        if detalle:
            for linea in detalle.splitlines():
                print(f"          {linea}")
    print(f"\nResumen: {fallos} fallos, {avisos} avisos, "
          f"{len(resultados) - fallos - avisos} correctos")

    return 2 if fallos else (1 if avisos else 0)


if __name__ == "__main__":
    sys.exit(main())
