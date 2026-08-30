#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Trae de Google Places las dos fotos que necesita cada centro.

Cada centro se ensena en dos sitios que piden cosas distintas:

    foto           -> EXTERIOR del edificio. Fondo a pantalla completa de <slug>.html.
    foto_interior  -> INTERIOR (sala de estudio). Cover del panel lateral del mapa.

Decidir cual de las fotos de un sitio es el interior no se puede automatizar: hay que
verlas. Por eso el trabajo va en tres pasos, y el del medio es humano:

    python fotos.py fetch  <slug>...          descarga hasta 10 fotos por centro
    python fotos.py sheet  <slug>...          monta una hoja de contactos por centro
    python fotos.py apply  elecciones.json    recorta, guarda en images/ y parchea index.html

La clave de API se lee de GOOGLE_PLACES_KEY o de ~/.bibliotecasmadrid-places.env.
Nunca de un archivo del repo: build.sh publica en dist/ todo lo que hay en el directorio.

Este script NO se publica: esta en la lista PRIVADO de build.sh.
"""

import argparse
import json
import math
import os
import re
import sys
import time
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont

import build

ROOT = Path(__file__).resolve().parent
IMAGENES = ROOT / "images"
INDEX = ROOT / "index.html"

# La cache va FUERA del repo, y en concreto fuera de OneDrive. Son ~5 MB por centro y
# 217 centros: cerca de 1 GB de material desechable que no pinta nada sincronizandose
# a la nube del usuario. Solo importa lo que acabe en images/. Se puede mover con
# FOTOS_CACHE si hiciera falta otro sitio.
CACHE = Path(os.environ.get("FOTOS_CACHE")
             or Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "bibliotecasmadrid-fotos")

# Emparejar una ficha de Maps con un centro nuestro es un juicio con dos senales:
# donde esta y como se llama. Solo con la distancia no se distingue una biblioteca con
# las coordenadas algo desviadas (nombre identico, 300 m) de otra biblioteca distinta
# del mismo municipio (nombre parecido, 2 km). Asi que:
#
#   - Si el nombre NO coincide, hay que estar muy cerca: 250 m.
#   - Si el nombre coincide en sus palabras distintivas, se admite hasta 3 km, que es
#     el margen que hace falta cuando el lat/lng de index.html apunta al centro del
#     municipio en vez de al edificio.
#
# Lo que nunca se acepta es un nombre que no casa y ademas lejos.
RADIO_MAX_M = 250
RADIO_CON_NOMBRE_M = 3000
RADIO_BUSQUEDA_M = 400.0

# Palabras que salen en casi todas las fichas y no distinguen nada.
VACIAS = {"biblioteca", "bibliotecas", "publica", "municipal", "de", "del", "la", "el",
          "los", "las", "y", "sala", "estudio", "centro", "cultural", "sociocultural",
          "madrid", "universidad", "campus", "facultad", "escuela", "general", "adultos"}


_MUNICIPIOS = None


def municipios():
    """Palabras de los municipios, sacadas de las propias direcciones de index.html.

    Hacen falta como palabras vacias: "Biblioteca Municipal de Guadarrama" se queda,
    quitado el ruido comun, en la sola palabra "guadarrama", y con eso casaria con
    cualquier otra biblioteca del pueblo. Si al quitarlas no sobra nada distintivo, es
    que el nombre no sirve para identificar: mejor exigir cercania.
    """
    global _MUNICIPIOS
    if _MUNICIPIOS is None:
        palabras = set()
        for d in catalogo().values():
            municipio = re.search(r"\d{5}\s+(.+?)\s*$", d.get("direccion", "") or "")
            if municipio:
                limpio = re.sub(r"[^a-z0-9 ]+", " ", normalizar_texto(municipio.group(1)))
                palabras.update(p for p in limpio.split() if len(p) > 2)
        _MUNICIPIOS = palabras
    return _MUNICIPIOS


def distintivas(texto):
    """Palabras con las que se reconoce un centro, sin el ruido comun a todos."""
    limpio = re.sub(r"[^a-z0-9 ]+", " ", normalizar_texto(texto))
    fuera = VACIAS | municipios()
    return {p for p in limpio.split() if len(p) > 2 and p not in fuera}


def normalizar_texto(texto):
    import unicodedata
    texto = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in texto if not unicodedata.combining(c)).lower()


def mismo_nombre(nuestro, suyo):
    """True si las palabras distintivas de uno estan contenidas en las del otro."""
    a, b = distintivas(nuestro), distintivas(suyo)
    if not a or not b:
        return False
    comunes = a & b
    # Basta con que el nombre corto quede cubierto: "Biblioteca Gloria Fuertes" contra
    # "Biblioteca Municipal Gloria Fuertes de Parla" comparte {gloria, fuertes}.
    return len(comunes) >= min(len(a), len(b)) and len(comunes) >= 1

# El cover del panel mide 160 px de alto; mas resolucion es peso muerto en el repo.
TAM_INTERIOR = (800, 500)
# El exterior va a pantalla completa, asi que necesita bastante mas.
ANCHO_EXTERIOR = 1600
CALIDAD = 82

# Una sala de estudio suele tener DOS fichas en Maps: la del centro cultural que la
# alberga y la de la sala. Las fotos utiles pueden estar en cualquiera de las dos, asi
# que se juntan todas las fichas dentro del radio.
#
# 10 es el maximo que devuelve Google por ficha. Estuvo en 8 mientras el limite era la
# cuota gratuita del SKU "Places API Place Details Photos" (1.000 llamadas al mes); con
# el credito promocional del proyecto eso deja de mandar, y mas fotos por centro es mas
# margen para acertar con el interior, que es donde se atasca la eleccion.
MAX_FOTOS = 10


# -- Clave de API -------------------------------------------------------------

# Se aceptan varios nombres para no tener que reescribir el archivo al cambiar de clave.
# El orden es una preferencia deliberada, de mejor a peor:
#   PROMO -> proyecto con credito promocional, es el que hay que gastar primero.
#   KEY   -> proyecto facturado de verdad; funciona, pero cobra al agotarse lo gratuito.
#   DEMO  -> inservible aqui: devuelve HTTP 200 pero omite el campo `photos`. Ultimo recurso.
NOMBRES_CLAVE = ("GOOGLE_PLACES_PROMO_KEY", "GOOGLE_PLACES_KEY", "GOOGLE_PLACES_DEMO_KEY")


def leer_clave():
    for nombre in NOMBRES_CLAVE:
        clave = os.environ.get(nombre, "").strip()
        if clave:
            return clave
    archivo = Path.home() / ".bibliotecasmadrid-places.env"
    if archivo.is_file():
        encontradas = {}
        for linea in archivo.read_text(encoding="utf-8-sig").splitlines():
            linea = linea.strip()
            if not linea or linea.startswith("#"):
                continue
            nombre, _, valor = linea.partition("=")
            nombre = nombre.strip()
            if nombre in NOMBRES_CLAVE:
                encontradas[nombre] = valor.strip().strip('"').strip("'")
        for nombre in NOMBRES_CLAVE:
            if encontradas.get(nombre):
                return encontradas[nombre]
    sys.exit(
        "ERROR: no hay clave de Google Places.\n"
        "  Ponla en la variable GOOGLE_PLACES_KEY, o crea el archivo\n"
        "  " + str(archivo) + "\n"
        "  con una linea:  GOOGLE_PLACES_KEY=tu_clave\n"
        "  Ese archivo va FUERA del repo a proposito: build.sh publica lo que hay dentro."
    )


# -- Catalogo de centros (index.html es la unica fuente) ----------------------

def catalogo():
    lugares = build.extract_lugares(str(INDEX))
    slugs = build.unique_slugs(lugares)
    return {slug: lugar for slug, lugar in zip(slugs, lugares)}


def metros(lat1, lng1, lat2, lng2):
    radio = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radio * math.asin(math.sqrt(a))


# -- fetch --------------------------------------------------------------------

class CuotaAgotada(RuntimeError):
    """Google ha dicho 429. Seguir con los demas centros solo gasta tiempo y ruido:
    una vez agotada la cuota del dia falla todo lo que venga detras. Mejor parar y
    que lo ya descargado quede en cache para reanudar."""


def buscar_sitios(sesion, clave, lugar):
    respuesta = sesion.post(
        "https://places.googleapis.com/v1/places:searchText",
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": clave,
            "X-Goog-FieldMask": "places.id,places.displayName,places.location,places.photos",
        },
        json={
            "textQuery": lugar["nombre"] + ", " + lugar["direccion"],
            "languageCode": "es",
            "maxResultCount": 10,
            "locationBias": {
                "circle": {
                    "center": {"latitude": lugar["lat"], "longitude": lugar["lng"]},
                    "radius": RADIO_BUSQUEDA_M,
                }
            },
        },
        timeout=30,
    )
    if respuesta.status_code == 429:
        raise CuotaAgotada(respuesta.text[:300])
    if respuesta.status_code != 200:
        raise RuntimeError("searchText %s: %s" % (respuesta.status_code, respuesta.text[:300]))

    sitios = respuesta.json().get("places") or []
    if not sitios:
        return None, "sin resultados"

    # Google ordena por relevancia, no por cercania: quedarse con el mas cercano de los
    # candidatos y comprobar despues que de verdad esta donde dice la ficha.
    def distancia(sitio):
        loc = sitio.get("location") or {}
        if "latitude" not in loc:
            return float("inf")
        return metros(lugar["lat"], lugar["lng"], loc["latitude"], loc["longitude"])

    def aceptable(sitio, dist):
        suyo = (sitio.get("displayName") or {}).get("text", "")
        if dist <= RADIO_MAX_M:
            return True
        return dist <= RADIO_CON_NOMBRE_M and mismo_nombre(lugar["nombre"], suyo)

    cerca = sorted(((s, distancia(s)) for s in sitios), key=lambda par: par[1])
    dentro = [s for s, d in cerca if aceptable(s, d)]
    if not dentro:
        sitio, lejania = cerca[0]
        nombre = (sitio.get("displayName") or {}).get("text", "?")
        return None, "el mas cercano (%s) esta a %.0f m y el nombre no casa" % (nombre, lejania)
    return dentro, None


def ficha_por_id(sesion, clave, place_id):
    """Trae una ficha concreta, saltandose la busqueda.

    Sirve para los centros donde el emparejamiento automatico no puede acertar: sobre
    todo bibliotecas renombradas (la direccion coincide al detalle pero el nombre que
    tiene Google es otro) y centros cuyas coordenadas en index.html estan mal, que es
    justo lo que hace fallar la comprobacion de distancia.
    """
    respuesta = sesion.get(
        "https://places.googleapis.com/v1/places/" + place_id,
        headers={"X-Goog-Api-Key": clave,
                 "X-Goog-FieldMask": "id,displayName,location,photos,formattedAddress"},
        timeout=30,
    )
    if respuesta.status_code == 429:
        raise CuotaAgotada(respuesta.text[:200])
    if respuesta.status_code != 200:
        raise RuntimeError("details %s: %s" % (respuesta.status_code, respuesta.text[:200]))
    return respuesta.json()


def url_de_foto(sesion, clave, nombre_foto, ancho):
    respuesta = sesion.get(
        "https://places.googleapis.com/v1/" + nombre_foto + "/media",
        params={"maxWidthPx": ancho, "skipHttpRedirect": "true", "key": clave},
        timeout=30,
    )
    if respuesta.status_code == 429:
        raise CuotaAgotada(respuesta.text[:200])
    if respuesta.status_code != 200:
        raise RuntimeError("media %s: %s" % (respuesta.status_code, respuesta.text[:200]))
    return respuesta.json()["photoUri"]


def autor(foto):
    atribuciones = foto.get("authorAttributions") or []
    if not atribuciones:
        return ""
    return atribuciones[0].get("displayName", "").strip()


def cmd_fetch(slugs, forzar=False, sitios=None):
    clave = leer_clave()
    centros = catalogo()
    sesion = requests.Session()
    problemas = []
    sitios = sitios or {}

    for slug in slugs:
        lugar = centros.get(slug)
        if lugar is None:
            problemas.append((slug, "no existe ese slug en index.html"))
            continue

        destino = CACHE / slug
        if (destino / "meta.json").is_file() and not forzar:
            print("  = %s: ya en cache (--forzar para rehacer)" % slug)
            continue

        try:
            if slug in sitios:
                encontrados = [ficha_por_id(sesion, clave, pid) for pid in sitios[slug]]
                motivo = None
            else:
                encontrados, motivo = buscar_sitios(sesion, clave, lugar)
        except CuotaAgotada as error:
            print("\n!! CUOTA AGOTADA en %s. Paro aqui; lo descargado sigue en cache." % slug)
            print("   %s" % error)
            problemas.append((slug, "cuota agotada"))
            break
        except Exception as error:                          # noqa: BLE001
            problemas.append((slug, str(error)))
            continue
        if encontrados is None:
            problemas.append((slug, motivo))
            continue

        # Intercalar las fotos de cada ficha en vez de encadenarlas: si el tope corta,
        # corta por el final de todas, no deja fuera la segunda ficha entera.
        por_ficha = [(s, list(s.get("photos") or [])) for s in encontrados]
        pila = []
        for vuelta in range(max((len(f) for _, f in por_ficha), default=0)):
            for sitio, fs in por_ficha:
                if vuelta < len(fs):
                    pila.append((sitio, fs[vuelta]))
        pila = pila[:MAX_FOTOS]
        if not pila:
            problemas.append((slug, "ninguna de las %d fichas cercanas tiene fotos" % len(encontrados)))
            continue

        destino.mkdir(parents=True, exist_ok=True)
        meta = {
            "slug": slug,
            "nombre": lugar["nombre"],
            "fichas": [{"place_id": s.get("id", ""),
                        "nombre": (s.get("displayName") or {}).get("text", "")}
                       for s, _ in por_ficha],
            "fotos": [],
        }

        cortado = False
        for indice, (sitio, foto) in enumerate(pila, start=1):
            try:
                uri = url_de_foto(sesion, clave, foto["name"], ANCHO_EXTERIOR)
                descarga = sesion.get(uri, timeout=60)
                descarga.raise_for_status()
            except CuotaAgotada as error:
                print("    !! %s: cuota de fotos agotada en la %d." % (slug, indice))
                print("       %s" % error)
                cortado = True
                break
            except Exception as error:                      # noqa: BLE001
                print("    ! %s foto %d: %s" % (slug, indice, error))
                continue
            archivo = destino / ("%02d.jpg" % indice)
            archivo.write_bytes(descarga.content)
            meta["fotos"].append({
                "n": indice,
                "archivo": archivo.name,
                "autor": autor(foto),
                "ficha": (sitio.get("displayName") or {}).get("text", ""),
                "ancho": foto.get("widthPx"),
                "alto": foto.get("heightPx"),
            })
            time.sleep(0.1)

        (destino / "meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        fichas = " + ".join(f["nombre"] for f in meta["fichas"])
        print("  + %s: %d fotos de %d ficha(s)  [%s]"
              % (slug, len(meta["fotos"]), len(meta["fichas"]), fichas))
        if cortado:
            # El meta ya esta escrito con lo que dio tiempo a bajar; --forzar lo rehace.
            problemas.append((slug, "incompleto: cuota agotada a mitad"))
            break

    if problemas:
        print("\nPara revisar a mano:")
        for slug, motivo in problemas:
            print("  - %s: %s" % (slug, motivo))
    return problemas


# -- sheet --------------------------------------------------------------------

def tipografia(tam):
    for ruta in ("C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf"):
        try:
            return ImageFont.truetype(ruta, tam)
        except OSError:
            continue
    return ImageFont.load_default()


def recortar(imagen, tam):
    """Recorta al centro para llenar exactamente tam, sin deformar."""
    ancho_destino, alto_destino = tam
    escala = max(ancho_destino / imagen.width, alto_destino / imagen.height)
    nuevo = (max(1, round(imagen.width * escala)), max(1, round(imagen.height * escala)))
    imagen = imagen.resize(nuevo, Image.LANCZOS)
    izquierda = (imagen.width - ancho_destino) // 2
    arriba = (imagen.height - alto_destino) // 2
    return imagen.crop((izquierda, arriba, izquierda + ancho_destino, arriba + alto_destino))


def cmd_sheet(slugs, salida):
    salida = Path(salida)
    salida.mkdir(parents=True, exist_ok=True)
    columnas, celda, margen, cabecera = 4, 320, 10, 46
    alto_celda = int(celda * 0.68)
    fuente_num = tipografia(30)
    fuente_tit = tipografia(20)
    hechas = []

    for slug in slugs:
        meta_ruta = CACHE / slug / "meta.json"
        if not meta_ruta.is_file():
            print("  ! %s: sin cache, pasa fetch primero" % slug)
            continue
        meta = json.loads(meta_ruta.read_text(encoding="utf-8"))
        fotos = meta["fotos"]
        if not fotos:
            print("  ! %s: cache sin fotos" % slug)
            continue

        filas = math.ceil(len(fotos) / columnas)
        ancho = columnas * celda + (columnas + 1) * margen
        alto = cabecera + filas * alto_celda + (filas + 1) * margen
        hoja = Image.new("RGB", (ancho, alto), (24, 28, 36))
        lapiz = ImageDraw.Draw(hoja)
        lapiz.text((margen, 12), slug + "  ·  " + meta["nombre"],
                   font=fuente_tit, fill=(235, 240, 248))

        for posicion, foto in enumerate(fotos):
            fila, columna = divmod(posicion, columnas)
            x = margen + columna * (celda + margen)
            y = cabecera + margen + fila * (alto_celda + margen)
            try:
                miniatura = Image.open(CACHE / slug / foto["archivo"]).convert("RGB")
            except OSError:
                continue
            hoja.paste(recortar(miniatura, (celda, alto_celda)), (x, y))
            # Numero grande sobre fondo opaco: es lo que se cita luego al elegir.
            lapiz.rectangle([x, y, x + 46, y + 40], fill=(15, 23, 42))
            lapiz.text((x + 13, y + 2), str(foto["n"]), font=fuente_num, fill=(255, 214, 102))

        ruta = salida / (slug + ".jpg")
        hoja.save(ruta, "JPEG", quality=88)
        hechas.append(ruta)
        print("  + %s" % ruta)
    return hechas


# -- apply --------------------------------------------------------------------

def guardar_interior(origen, destino):
    imagen = Image.open(origen).convert("RGB")
    recortar(imagen, TAM_INTERIOR).save(destino, "JPEG", quality=CALIDAD, optimize=True)


def guardar_exterior(origen, destino):
    imagen = Image.open(origen).convert("RGB")
    # Limitar el lado LARGO, no el ancho: una foto vertical con el ancho a 1600 se va a
    # 1600x2133, medio mega para un fondo que ademas se recorta con object-fit: cover.
    largo = max(imagen.width, imagen.height)
    if largo > ANCHO_EXTERIOR:
        escala = ANCHO_EXTERIOR / largo
        imagen = imagen.resize((round(imagen.width * escala), round(imagen.height * escala)),
                               Image.LANCZOS)
    # Progresivo: el fondo ocupa toda la pantalla y tarda; asi se ve entero enseguida
    # aunque borroso, en vez de ir apareciendo por franjas de arriba abajo.
    imagen.save(destino, "JPEG", quality=CALIDAD, optimize=True, progressive=True)


def fijar_campo(linea, campo, valor):
    """Pone campo: "valor" en la linea de un objeto de `lugares`, creandolo si falta."""
    patron = re.compile(r'(?<![\w])' + campo + r':\s*"(?:[^"\\]|\\.)*"')
    nuevo = campo + ': "' + valor + '"'
    if patron.search(linea):
        return patron.sub(lambda _: nuevo, linea, count=1)
    # Nuevo: colgarlo detras de `foto`, que es donde vive el resto de lo visual.
    ancla = re.compile(r'(?<![\w])foto:\s*"(?:[^"\\]|\\.)*"')
    coincidencia = ancla.search(linea)
    if coincidencia is None:
        raise ValueError("la linea no tiene campo foto donde anclar " + campo)
    fin = coincidencia.end()
    return linea[:fin] + ", " + nuevo + linea[fin:]


def cmd_apply(ruta_elecciones):
    elecciones = json.loads(Path(ruta_elecciones).read_text(encoding="utf-8"))
    centros = catalogo()
    IMAGENES.mkdir(exist_ok=True)

    with INDEX.open(encoding="utf-8", newline="") as fuente:
        texto = fuente.read()
    salto = "\r\n" if "\r\n" in texto else "\n"
    lineas = texto.split(salto)
    cambios = 0

    for slug, eleccion in elecciones.items():
        lugar = centros.get(slug)
        if lugar is None:
            print("  ! %s: no existe ese slug" % slug)
            continue
        meta_ruta = CACHE / slug / "meta.json"
        if not meta_ruta.is_file():
            print("  ! %s: sin cache" % slug)
            continue
        meta = json.loads(meta_ruta.read_text(encoding="utf-8"))
        por_numero = {foto["n"]: foto for foto in meta["fotos"]}

        # La linea del objeto se localiza por su nombre exacto, nunca por posicion.
        aguja = 'nombre: "' + lugar["nombre"] + '"'
        indices = [n for n, linea in enumerate(lineas) if aguja in linea]
        if len(indices) != 1:
            print("  ! %s: %d lineas con ese nombre, no se toca" % (slug, len(indices)))
            continue
        n_linea = indices[0]
        linea = lineas[n_linea]

        for clase, campo, credito, guardar in (
            ("interior", "foto_interior", "foto_interior_credito", guardar_interior),
            ("exterior", "foto", "foto_credito", guardar_exterior),
        ):
            numero = eleccion.get(clase)
            if not numero:
                continue
            foto = por_numero.get(numero)
            if foto is None:
                print("  ! %s: no hay foto %s para %s" % (slug, numero, clase))
                continue
            nombre_archivo = "%s-%s.jpg" % (slug, clase)
            guardar(CACHE / slug / foto["archivo"], IMAGENES / nombre_archivo)
            linea = fijar_campo(linea, campo, "images/" + nombre_archivo)
            if foto["autor"]:
                linea = fijar_campo(linea, credito, foto["autor"].replace('"', "'"))
            kb = (IMAGENES / nombre_archivo).stat().st_size / 1024
            print("  + %s  (%.0f KB, foto %s, %s)"
                  % (nombre_archivo, kb, numero, foto["autor"] or "sin autor"))

        lineas[n_linea] = linea
        cambios += 1

    if cambios:
        with INDEX.open("w", encoding="utf-8", newline="") as destino:
            destino.write(salto.join(lineas))
        print("\nindex.html actualizado: %d centros. Ahora: python build.py" % cambios)
    else:
        print("\nSin cambios.")


# -- CLI ----------------------------------------------------------------------

def main():
    # Los nombres de autor de Google traen de todo (polaco, griego, chino) y la consola
    # de Windows va en cp1252: sin esto, un solo caracter raro aborta el proceso entero
    # a mitad de trabajo.
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    principal = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = principal.add_subparsers(dest="orden", required=True)

    p = sub.add_parser("fetch", help="descarga las fotos de Google Places a .fotos-cache/")
    p.add_argument("slugs", nargs="+")
    p.add_argument("--forzar", action="store_true", help="rehacer aunque ya esten en cache")
    p.add_argument("--sitios", help='JSON: {"slug": ["place_id", ...]} para saltarse la busqueda')

    p = sub.add_parser("sheet", help="monta la hoja de contactos para elegir")
    p.add_argument("slugs", nargs="+")
    p.add_argument("--salida", default=str(CACHE / "_hojas"))

    p = sub.add_parser("apply", help="recorta a images/ y parchea index.html")
    p.add_argument("elecciones", help='JSON: {"slug": {"interior": 3, "exterior": 1}}')

    p = sub.add_parser("slugs", help="lista los slugs de index.html")
    p.add_argument("--tipo", choices=("biblioteca", "sala", "universidad"))

    args = principal.parse_args()
    if args.orden == "fetch":
        forzadas = {}
        if args.sitios:
            forzadas = json.loads(Path(args.sitios).read_text(encoding="utf-8"))
        cmd_fetch(args.slugs, args.forzar, forzadas)
    elif args.orden == "sheet":
        cmd_sheet(args.slugs, args.salida)
    elif args.orden == "apply":
        cmd_apply(args.elecciones)
    elif args.orden == "slugs":
        for slug, lugar in catalogo().items():
            if args.tipo and lugar["tipo"] != args.tipo:
                continue
            print("%s\t%s\t%s" % (slug, lugar["tipo"], lugar["nombre"]))


if __name__ == "__main__":
    main()
