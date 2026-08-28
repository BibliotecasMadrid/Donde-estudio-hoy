#!/usr/bin/env python3
"""
build.py - Generador estático para "Dónde estudiar en Madrid".

Lee el array `lugares` de index.html y genera:
  1. Un archivo <slug>.html para cada centro (ej. clara-campoamor.html).
  2. sitemap.xml con la home + todos los centros.

Uso:
  python build.py
"""

import argparse
import copy
import datetime as dt
import json
import re
import os
import html
import unicodedata
from urllib.parse import quote_plus, urlparse

BASE = "https://bibliotecasmadrid.es/"
LASTMOD = "2026-08-27"

WEEKEND_ROUTE = "bibliotecas-abiertas-fin-de-semana-madrid"
FULL_DAY_ROUTE = "bibliotecas-24-horas-madrid"

PREFIJOS = [
    "biblioteca pública ",
    "biblioteca municipal ",
    "salas de estudio ",
    "sala de estudio del ",
    "sala de estudio de la ",
    "sala de estudio ",
    "sala de lectura ",
    "biblioteca ",
]

COLORES = {
    "biblioteca": {"fill": "#2563EB", "label": "Biblioteca"},
    "sala":       {"fill": "#059669", "label": "Sala de estudio"},
    "universidad":{"fill": "#7C3AED", "label": "Biblioteca universitaria"},
}

ROOT = os.path.dirname(os.path.abspath(__file__))
CALENDARIO_PATH = os.path.join(ROOT, "calendario.json")
HORARIOS_DIR = os.path.join(ROOT, "horarios")
CALENDAR_SCHEMA_VERSION = 2
PUBLIC_CALENDAR_VERSION = 1
TIMEZONE = "Europe/Madrid"

# DÃ­as con el formato de ``datetime.date.weekday()``: lunes=0, domingo=6.
# El JSON pÃºblico usa las mismas claves; asÃ­ no hay conversiÃ³n ambigua entre
# Python y JavaScript.
WEEKDAYS = tuple(range(7))
ESTADOS = {"abierto", "cerrado", "consultar"}

# Fiestas autonÃ³micas y nacionales comunes a toda la Comunidad de Madrid. Las
# fiestas locales no se mezclan aquÃ­: cada municipio las declara por separado
# en la fuente v2. Fuente: BOE-A-2025-21667 / Decreto 75/2025 de la CAM.
FESTIVOS_REGIONALES_2026 = {
    "2026-01-01": "AÃ±o Nuevo",
    "2026-01-06": "EpifanÃ­a del SeÃ±or",
    "2026-04-02": "Jueves Santo",
    "2026-04-03": "Viernes Santo",
    "2026-05-01": "Fiesta del Trabajo",
    "2026-05-02": "Fiesta de la Comunidad de Madrid",
    "2026-08-15": "AsunciÃ³n de la Virgen",
    "2026-10-12": "Fiesta Nacional de EspaÃ±a",
    "2026-11-02": "Traslado de Todos los Santos",
    "2026-12-07": "Traslado del DÃ­a de la ConstituciÃ³n EspaÃ±ola",
    "2026-12-08": "Inmaculada ConcepciÃ³n",
    "2026-12-25": "Natividad del SeÃ±or",
}

# ResoluciÃ³n de 2 de diciembre de 2025, D. G. de Trabajo (BOCM 12/12/2025).
# Solo se incluyen municipios presentes en el mapa. Mantener este mapa evita
# aplicar, por error, San Isidro a bibliotecas de otros municipios.
FESTIVOS_LOCALES_2026 = {
    "alcala-de-henares": {"2026-08-06": "Fiesta local de AlcalÃ¡ de Henares", "2026-10-09": "Fiesta local de AlcalÃ¡ de Henares"},
    "alcobendas": {"2026-01-24": "Fiesta local de Alcobendas", "2026-05-15": "Fiesta local de Alcobendas"},
    "alcorcon": {"2026-04-06": "Fiesta local de AlcorcÃ³n", "2026-09-08": "Fiesta local de AlcorcÃ³n"},
    "aranjuez": {"2026-05-29": "Fiesta local de Aranjuez", "2026-09-04": "Fiesta local de Aranjuez"},
    "arganda-del-rey": {"2026-09-11": "Fiesta local de Arganda del Rey", "2026-09-14": "Fiesta local de Arganda del Rey"},
    "boadilla-del-monte": {"2026-06-01": "Fiesta local de Boadilla del Monte", "2026-10-05": "Fiesta local de Boadilla del Monte"},
    "collado-villalba": {"2026-06-12": "Fiesta local de Collado Villalba", "2026-07-24": "Fiesta local de Collado Villalba"},
    "colmenar-viejo": {"2026-08-31": "Fiesta local de Colmenar Viejo", "2026-09-01": "Fiesta local de Colmenar Viejo"},
    "colmenarejo": {"2026-05-15": "Fiesta local de Colmenarejo", "2026-07-24": "Fiesta local de Colmenarejo"},
    "coslada": {"2026-05-15": "Fiesta local de Coslada", "2026-06-15": "Fiesta local de Coslada"},
    "fuenlabrada": {"2026-09-14": "Fiesta local de Fuenlabrada", "2026-12-26": "Fiesta local de Fuenlabrada"},
    "galapagar": {"2026-05-15": "Fiesta local de Galapagar", "2026-09-14": "Fiesta local de Galapagar"},
    "getafe": {"2026-05-14": "Fiesta local de Getafe", "2026-05-25": "Fiesta local de Getafe"},
    "guadarrama": {"2026-09-29": "Fiesta local de Guadarrama", "2026-10-05": "Fiesta local de Guadarrama"},
    "las-rozas-de-madrid": {"2026-05-04": "Fiesta local de Las Rozas de Madrid", "2026-09-29": "Fiesta local de Las Rozas de Madrid"},
    "leganes": {"2026-08-14": "Fiesta local de LeganÃ©s", "2026-10-09": "Fiesta local de LeganÃ©s"},
    "majadahonda": {"2026-09-14": "Fiesta local de Majadahonda", "2026-11-25": "Fiesta local de Majadahonda"},
    "madrid": {"2026-05-15": "San Isidro", "2026-11-09": "Nuestra SeÃ±ora de la Almudena"},
    "mostoles": {"2026-05-15": "Fiesta local de MÃ³stoles", "2026-09-12": "Fiesta local de MÃ³stoles"},
    "navalcarnero": {"2026-05-15": "Fiesta local de Navalcarnero", "2026-09-08": "Fiesta local de Navalcarnero"},
    "parla": {"2026-06-15": "Fiesta local de Parla", "2026-09-14": "Fiesta local de Parla"},
    "pinto": {"2026-03-19": "Fiesta local de Pinto", "2026-05-15": "Fiesta local de Pinto"},
    "pozuelo-de-alarcon": {"2026-07-16": "Fiesta local de Pozuelo de AlarcÃ³n", "2026-09-07": "Fiesta local de Pozuelo de AlarcÃ³n"},
    "rivas-vaciamadrid": {"2026-05-14": "Fiesta local de Rivas-Vaciamadrid", "2026-05-15": "Fiesta local de Rivas-Vaciamadrid"},
    "san-fernando-de-henares": {"2026-05-15": "Fiesta local de San Fernando de Henares", "2026-05-29": "Fiesta local de San Fernando de Henares"},
    "san-lorenzo-de-el-escorial": {"2026-08-10": "Fiesta local de San Lorenzo de El Escorial", "2026-09-14": "Fiesta local de San Lorenzo de El Escorial"},
    "san-sebastian-de-los-reyes": {"2026-01-20": "Fiesta local de San SebastiÃ¡n de los Reyes", "2026-08-28": "Fiesta local de San SebastiÃ¡n de los Reyes"},
    "torrejon-de-ardoz": {"2026-06-22": "Fiesta local de TorrejÃ³n de Ardoz", "2026-06-23": "Fiesta local de TorrejÃ³n de Ardoz"},
    "torrelodones": {"2026-07-16": "Fiesta local de Torrelodones", "2026-08-14": "Fiesta local de Torrelodones"},
    "tres-cantos": {"2026-03-21": "Fiesta local de Tres Cantos", "2026-06-24": "Fiesta local de Tres Cantos"},
    "valdemoro": {"2026-05-11": "Fiesta local de Valdemoro", "2026-09-08": "Fiesta local de Valdemoro"},
    "villa-del-prado": {"2026-04-06": "Fiesta local de Villa del Prado", "2026-09-08": "Fiesta local de Villa del Prado"},
    "villanueva-de-la-canada": {"2026-05-15": "Fiesta local de Villanueva de la CaÃ±ada", "2026-07-24": "Fiesta local de Villanueva de la CaÃ±ada"},
    "villaviciosa-de-odon": {"2026-01-20": "Fiesta local de Villaviciosa de OdÃ³n", "2026-09-21": "Fiesta local de Villaviciosa de OdÃ³n"},
}

def slugify(nombre):
    base = nombre
    low = nombre.lower()
    for p in PREFIJOS:
        if low.startswith(p):
            base = nombre[len(p):]
            break
    base = unicodedata.normalize("NFKD", base)
    base = "".join(c for c in base if not unicodedata.combining(c)).lower()
    base = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
    return base or "centro"


def unique_slugs(lugares):
    seen = {}
    out = []
    for d in lugares:
        s = slugify(d["nombre"])
        if s in seen:
            seen[s] += 1
            s = f"{s}-{seen[s]}"
        else:
            seen[s] = 1
        out.append(s)
    return out


def extract_lugares(index_html):
    with open(index_html, encoding="utf-8") as f:
        src = f.read()
    i = src.index("const lugares = [")
    arr_start = src.index("[", i)
    end = src.index("\n];", arr_start)
    body = src[arr_start + 1:end]
    body = "\n".join(ln for ln in body.split("\n") if not ln.strip().startswith("//"))
    body = re.sub(r'(?<![\w"])(tipo|nombre|distrito|direccion|lat|lng|plazas|foto|horario|web|libcal_lid|libcal_iid)\s*:',
                  r'"\1":', body)
    jtext = "[" + body + "]"
    jtext = re.sub(r",(\s*[}\]])", r"\1", jtext)
    return json.loads(jtext)


# ─────────────────────────────────────────────────────────────
#  CALENDARIOS DIARIOS COMPILADOS
#
#  ``calendario.json`` es la fuente editable y declara un perfil
#  explícito por centro. Durante la migración inicial se extraen las
#  83 pautas que ya estaban publicadas en ``lugares[].horario``. Esa
#  lectura sólo sirve para crear la fuente v2: el sitio publicado no
#  vuelve a interpretar dicho texto para saber si un centro abre.
# ─────────────────────────────────────────────────────────────


def normalizar(texto):
    texto = unicodedata.normalize("NFKD", texto or "")
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return texto.lower().replace("–", "-").replace("—", "-").strip()


def identificador(texto):
    return re.sub(r"[^a-z0-9]+", "-", normalizar(texto)).strip("-")


def minuto(hora):
    if not isinstance(hora, str) or not re.fullmatch(r"(?:[01]?\d|2[0-4]):[0-5]\d", hora):
        raise ValueError(f"Hora inválida: {hora!r}")
    h, m = (int(p) for p in hora.split(":"))
    if h == 24 and m:
        raise ValueError(f"24:00 es la única hora válida con 24: {hora!r}")
    return h * 60 + m


def normalizar_intervalos(intervalos):
    if not intervalos:
        return []
    if not isinstance(intervalos, list):
        raise ValueError("Los intervalos deben ser una lista")
    resultado = []
    ultimo_fin = -1
    for intervalo in intervalos:
        if not isinstance(intervalo, (list, tuple)) or len(intervalo) != 2:
            raise ValueError(f"Intervalo inválido: {intervalo!r}")
        inicio, fin = intervalo
        inicio_min, fin_min = minuto(inicio), minuto(fin)
        if inicio_min >= fin_min:
            raise ValueError(f"Intervalo sin duración: {intervalo!r}")
        if inicio_min < ultimo_fin:
            raise ValueError(f"Intervalos solapados: {intervalos!r}")
        resultado.append([inicio, fin])
        ultimo_fin = fin_min
    return resultado


def entrada(estado, intervalos=None, nota=None):
    if estado not in ESTADOS:
        raise ValueError(f"Estado de calendario inválido: {estado!r}")
    intervalos = normalizar_intervalos(intervalos or [])
    if estado == "abierto" and not intervalos:
        raise ValueError("Una entrada abierta debe incluir al menos un intervalo")
    if estado != "abierto":
        intervalos = []
    resultado = {"estado": estado, "intervalos": intervalos}
    if nota:
        resultado["nota"] = str(nota)
    return resultado


def intervalos_de_texto(texto):
    """Extrae franjas de un horario heredado; sólo se usa al migrar."""
    salida = []
    patron = re.compile(r"(?<!\d)(\d{1,2})(?::(\d{2}))?\s*(?:-|a)\s*(\d{1,2})(?::(\d{2}))?\s*h?", re.I)
    for match in patron.finditer(normalizar(texto)):
        h1, m1, h2, m2 = match.groups()
        inicio = f"{int(h1):02d}:{int(m1 or 0):02d}"
        fin = f"{int(h2):02d}:{int(m2 or 0):02d}"
        try:
            salida.append([inicio, fin])
        except ValueError:
            continue
    try:
        return normalizar_intervalos(salida)
    except ValueError:
        # Un texto editorial mal ordenado no debe impedir crear una fuente
        # revisable: se marca como consultar en vez de inventar una apertura.
        return []


def dias_de_segmento(segmento):
    """Devuelve días Python (lunes=0 … domingo=6) mencionados en un segmento."""
    s = normalizar(segmento)
    patrones = [
        (r"lun(?:es)?\s*(?:-|a)\s*dom(?:ingo)?", range(7)),
        (r"lun(?:es)?\s*(?:-|a)\s*sab(?:ado)?", range(6)),
        (r"lun(?:es)?\s*(?:-|a)\s*vie(?:rnes)?", range(5)),
        (r"mar(?:tes)?\s*(?:-|a)\s*sab(?:ado)?", range(1, 6)),
        (r"lun(?:es)?\s*(?:-|a)\s*jue(?:ves)?", range(4)),
        (r"jue(?:ves)?\s*(?:-|a)\s*vie(?:rnes)?", range(3, 5)),
        (r"sab(?:ado)?\s*(?:-|a)\s*dom(?:ingo)?", (5, 6)),
    ]
    for patron, dias in patrones:
        if re.search(patron, s):
            return list(dias)
    if "fin de semana" in s or "fines de semana" in s:
        return [5, 6]
    dias = []
    nombres = (("lun", 0), ("mar", 1), ("mie", 2), ("jue", 3), ("vie", 4), ("sab", 5), ("dom", 6))
    for nombre, indice in nombres:
        if re.search(rf"\b{nombre}", s):
            dias.append(indice)
    return dias


def horario_semanal_heredado(texto):
    """Convierte el primer horario editorial en una pauta semanal explícita."""
    cerrado = entrada("cerrado", nota="Cerrado según horario habitual")
    semanal = {str(dia): copy.deepcopy(cerrado) for dia in WEEKDAYS}
    if "consultar" in normalizar(texto) or "telefono" in normalizar(texto):
        return {str(dia): entrada("consultar", nota="Consultar horario por teléfono") for dia in WEEKDAYS}

    linea = (texto or "").split("\n", 1)[0]
    segmentos = re.split(r"\s*[·;]\s*", linea)
    asignado = set()
    for segmento in segmentos:
        dias = dias_de_segmento(segmento)
        franjas = intervalos_de_texto(segmento)
        if not dias or not franjas:
            continue
        for dia in dias:
            semanal[str(dia)] = entrada("abierto", franjas, "Horario habitual")
            asignado.add(dia)

    # Algunos textos cortos sólo contienen una franja sin prefijo de días.
    if not asignado:
        franjas = intervalos_de_texto(linea)
        if franjas:
            for dia in range(5):
                semanal[str(dia)] = entrada("abierto", franjas, "Horario habitual")
    return semanal


def municipio_de_direccion(direccion):
    """Obtiene el municipio de la dirección postal, nunca del campo distrito."""
    match = re.search(r"\b\d{5}\s+([^,]+?)\s*$", direccion or "")
    nombre = match.group(1).strip() if match else "Madrid"
    return identificador(nombre) or "madrid"


def operador_de_url(url):
    host = urlparse(url or "").netloc.lower()
    if "madrid.es" in host:
        return "ayuntamiento-madrid"
    if "biblioagenda" in host:
        return "libcal"
    if host:
        return host.removeprefix("www.")
    return "sin-fuente"


def regla_desde_periodo(inicio, fin, estado, intervalos=None, nota=None, dias=None, prioridad=0):
    regla = {
        "from": f"2026-{inicio}",
        "to": f"2026-{fin}",
        "estado": estado,
        "intervalos": intervalos or [],
        "priority": prioridad,
    }
    if dias is not None:
        regla["weekdays"] = list(dias)
    if nota:
        regla["nota"] = nota
    return regla


def reglas_heredadas(excepciones):
    """Traduce las excepciones existentes a reglas fechadas de la fuente v2."""
    reglas = []
    if not excepciones:
        return reglas
    cierre = excepciones.get("summer_closure")
    if cierre:
        reglas.append(regla_desde_periodo(cierre["start"], cierre["end"], "cerrado", nota="Cierre de verano", prioridad=70))
    verano = excepciones.get("summer_period")
    if verano:
        for dias, clave in ((range(5), "weekday_schedule"), ((5,), "saturday_schedule"), ((6,), "sunday_schedule")):
            texto = verano.get(clave)
            franjas = intervalos_de_texto(texto or "")
            if franjas:
                reglas.append(regla_desde_periodo(verano["start"], verano["end"], "abierto", franjas, "Horario de verano", dias, 60))
            elif clave != "weekday_schedule":
                reglas.append(regla_desde_periodo(verano["start"], verano["end"], "cerrado", nota="Cerrado en horario de verano", dias=dias, prioridad=60))
    agosto = excepciones.get("august_schedule")
    if agosto:
        reglas.append(regla_desde_periodo(agosto["closure_start"], agosto["closure_end"], "cerrado", nota="Cierre de agosto", prioridad=70))
        if agosto.get("reduced_start") and agosto.get("reduced_end"):
            franjas = intervalos_de_texto(agosto.get("reduced_schedule", ""))
            if franjas:
                reglas.append(regla_desde_periodo(agosto["reduced_start"], agosto["reduced_end"], "abierto", franjas, "Horario reducido de agosto", range(5), 80))
    for periodo in excepciones.get("exam_periods", []):
        texto = periodo.get("schedule", "")
        if "24" in normalizar(texto):
            franjas = [["00:00", "24:00"]]
        else:
            franjas = intervalos_de_texto(texto)
        if franjas:
            reglas.append(regla_desde_periodo(periodo["start"], periodo["end"], "abierto", franjas, "Horario ampliado de exámenes", prioridad=90))
        else:
            reglas.append(regla_desde_periodo(periodo["start"], periodo["end"], "consultar", nota="Horario de exámenes por confirmar", prioridad=90))
    return reglas


def migrar_calendario(lugares, slugs, legacy):
    """Crea una fuente v2 completa sin perder las excepciones ya publicadas."""
    perfiles = {}
    excepciones = legacy.get("places_exceptions", {})
    fecha_revision = legacy.get("last_updated") or dt.date.today().isoformat()
    for lugar, slug in zip(lugares, slugs):
        horario_normalizado = normalizar(lugar.get("horario", ""))
        politica = "open" if "festivos" in horario_normalizado and "cerrado" not in horario_normalizado else "closed"
        perfil = {
            "municipio": municipio_de_direccion(lugar.get("direccion", "")),
            "operador": operador_de_url(lugar.get("web", "")),
            "source": {
                "url": lugar.get("web") or web_url(lugar)[0],
                "checked_at": fecha_revision,
                "confidence": "migrated-from-published-schedule",
            },
            "holiday_policy": politica,
            "weekly": horario_semanal_heredado(lugar.get("horario", "")),
            "rules": reglas_heredadas(excepciones.get(slug, {})),
            "dates": {},
        }
        # Las vísperas generales existentes no describen una hora única. No
        # se inventa: se expone como consultar hasta que el perfil la concrete.
        for fecha, texto in (legacy.get("special_eves") or {}).items():
            perfil["dates"][fecha] = entrada("consultar", nota=texto)
        perfiles[slug] = perfil
    return {
        "schema_version": CALENDAR_SCHEMA_VERSION,
        "year": 2026,
        "last_updated": fecha_revision,
        "time_zone": TIMEZONE,
        "regional_holidays": FESTIVOS_REGIONALES_2026,
        "municipal_holidays": FESTIVOS_LOCALES_2026,
        "places": perfiles,
    }


def cargar_calendario():
    with open(CALENDARIO_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def validar_perfil(slug, perfil, year):
    errores = []
    if not perfil.get("municipio"):
        errores.append(f"{slug}: falta municipio")
    source = perfil.get("source") or {}
    if not source.get("url") or not source.get("checked_at"):
        errores.append(f"{slug}: falta fuente o fecha de revisión")
    else:
        if urlparse(source["url"]).scheme != "https":
            errores.append(f"{slug}: la fuente debe usar HTTPS")
        try:
            dt.date.fromisoformat(source["checked_at"])
        except (TypeError, ValueError):
            errores.append(f"{slug}: fecha de revisión inválida")
    if perfil.get("holiday_policy") not in {"closed", "open", "unknown"}:
        errores.append(f"{slug}: holiday_policy inválida")
    weekly = perfil.get("weekly") or {}
    for dia in WEEKDAYS:
        if str(dia) not in weekly:
            errores.append(f"{slug}: falta el día semanal {dia}")
            continue
        try:
            entrada(weekly[str(dia)].get("estado"), weekly[str(dia)].get("intervalos"), weekly[str(dia)].get("nota"))
        except (AttributeError, ValueError) as exc:
            errores.append(f"{slug}: horario semanal {dia}: {exc}")
    for regla in perfil.get("rules", []):
        try:
            inicio = dt.date.fromisoformat(regla["from"])
            fin = dt.date.fromisoformat(regla["to"])
            if inicio.year != year or fin.year != year or inicio > fin:
                raise ValueError("rango de fechas inválido")
            if any(dia not in WEEKDAYS for dia in regla.get("weekdays", WEEKDAYS)):
                raise ValueError("weekdays inválido")
            entrada(regla["estado"], regla.get("intervalos"), regla.get("nota"))
            if regla.get("estado") == "abierto" and regla.get("intervalos") == [["00:00", "24:00"]]:
                fuente_regla = regla.get("source") or {}
                if urlparse(fuente_regla.get("url", "")).scheme != "https":
                    raise ValueError("la regla 24 h necesita una fuente HTTPS")
                revision = dt.date.fromisoformat(fuente_regla.get("checked_at", ""))
                if revision > dt.date.today():
                    raise ValueError("la fuente de la regla 24 h tiene una fecha futura")
        except (KeyError, TypeError, ValueError) as exc:
            errores.append(f"{slug}: regla inválida: {exc}")
    for fecha, valor in (perfil.get("dates") or {}).items():
        try:
            if dt.date.fromisoformat(fecha).year != year:
                raise ValueError("fecha fuera del año")
            entrada(valor["estado"], valor.get("intervalos"), valor.get("nota"))
        except (KeyError, TypeError, ValueError) as exc:
            errores.append(f"{slug}: fecha {fecha}: {exc}")
    return errores


def validar_calendario(calendario, slugs):
    errores = []
    if calendario.get("schema_version") != CALENDAR_SCHEMA_VERSION:
        errores.append("calendario.json no usa schema_version 2")
    year = calendario.get("year")
    if not isinstance(year, int):
        errores.append("year debe ser un entero")
        return errores
    if calendario.get("time_zone") != TIMEZONE:
        errores.append(f"time_zone debe ser {TIMEZONE}")
    for fecha, nombre in (calendario.get("regional_holidays") or {}).items():
        try:
            if dt.date.fromisoformat(fecha).year != year or not str(nombre).strip():
                raise ValueError
        except (TypeError, ValueError):
            errores.append(f"festivo regional inválido: {fecha}")
    for municipio, festivos in (calendario.get("municipal_holidays") or {}).items():
        if not municipio or not isinstance(festivos, dict):
            errores.append(f"festivos municipales inválidos: {municipio}")
            continue
        for fecha, nombre in festivos.items():
            try:
                if dt.date.fromisoformat(fecha).year != year or not str(nombre).strip():
                    raise ValueError
            except (TypeError, ValueError):
                errores.append(f"festivo de {municipio} inválido: {fecha}")
    perfiles = calendario.get("places") or {}
    esperados = set(slugs)
    if set(perfiles) != esperados:
        faltan = sorted(esperados - set(perfiles))
        sobran = sorted(set(perfiles) - esperados)
        if faltan:
            errores.append("faltan perfiles: " + ", ".join(faltan[:8]))
        if sobran:
            errores.append("hay perfiles sin centro: " + ", ".join(sobran[:8]))
    for slug in slugs:
        if slug in perfiles:
            errores.extend(validar_perfil(slug, perfiles[slug], year))
            if perfiles[slug].get("municipio") not in (calendario.get("municipal_holidays") or {}):
                errores.append(f"{slug}: municipio sin calendario de festivos")
    return errores


def fecha_es_festivo(fecha, perfil, calendario):
    clave = fecha.isoformat()
    if clave in (calendario.get("regional_holidays") or {}):
        return calendario["regional_holidays"][clave]
    municipio = perfil.get("municipio")
    return (calendario.get("municipal_holidays") or {}).get(municipio, {}).get(clave)


def resolver_dia(perfil, fecha, calendario):
    clave = fecha.isoformat()
    fechas = perfil.get("dates") or {}
    if clave in fechas:
        valor = fechas[clave]
        return entrada(valor["estado"], valor.get("intervalos"), valor.get("nota"))

    # Las reglas del propio centro (verano, exámenes o cierres temporales)
    # son excepciones oficiales y prevalecen sobre el cierre por festivo.
    candidatas = []
    for indice, regla in enumerate(perfil.get("rules") or []):
        inicio = dt.date.fromisoformat(regla["from"])
        fin = dt.date.fromisoformat(regla["to"])
        if inicio <= fecha <= fin and fecha.weekday() in regla.get("weekdays", WEEKDAYS):
            candidatas.append((int(regla.get("priority", 0)), indice, regla))
    if candidatas:
        _, _, regla = max(candidatas, key=lambda valor: (valor[0], valor[1]))
        return entrada(regla["estado"], regla.get("intervalos"), regla.get("nota"))

    # Sin una excepción del centro, el festivo regional o local cierra
    # por defecto. Los perfiles que abren en festivo usan policy=open.
    festivo = fecha_es_festivo(fecha, perfil, calendario)
    if festivo and perfil.get("holiday_policy") == "closed":
        return entrada("cerrado", nota=f"Cerrado por festivo ({festivo})")
    if festivo and perfil.get("holiday_policy") == "unknown":
        return entrada("consultar", nota=f"Horario por confirmar en festivo ({festivo})")

    valor = (perfil.get("weekly") or {}).get(str(fecha.weekday()))
    if not valor:
        return entrada("consultar", nota="Horario semanal pendiente de confirmar")
    return entrada(valor["estado"], valor.get("intervalos"), valor.get("nota"))


def generar_calendarios_publicos(calendario, slugs):
    """Materializa 12 JSON mensuales; la web consulta por slug + día."""
    year = calendario["year"]
    perfiles = calendario["places"]
    os.makedirs(HORARIOS_DIR, exist_ok=True)
    total = 0
    for mes in range(1, 13):
        primer_dia = dt.date(year, mes, 1)
        siguiente = dt.date(year + (mes == 12), 1 if mes == 12 else mes + 1, 1)
        dias = (siguiente - primer_dia).days
        datos = {
            "version": PUBLIC_CALENDAR_VERSION,
            "year": year,
            "month": mes,
            "time_zone": TIMEZONE,
            "places": {},
        }
        for slug in slugs:
            valores = [resolver_dia(perfiles[slug], primer_dia + dt.timedelta(days=offset), calendario) for offset in range(dias)]
            if len(valores) != dias:
                raise ValueError(f"{slug}: cobertura incompleta del mes {mes}")
            datos["places"][slug] = valores
            total += len(valores)
        destino = os.path.join(HORARIOS_DIR, f"{year}-{mes:02d}.json")
        with open(destino, "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False, separators=(",", ":"))
    esperado = len(slugs) * (366 if dt.date(year, 12, 31).timetuple().tm_yday == 366 else 365)
    if total != esperado:
        raise ValueError(f"Cobertura inválida: {total} días generados, se esperaban {esperado}")
    return total


def web_url(d):
    if d.get("web"):
        return d["web"], "Web oficial"
    return "https://www.google.com/search?q=" + quote_plus(d["nombre"] + " Madrid"), "Buscar web y horario"


def page_html(d, slug):
    c = COLORES[d["tipo"]]
    e = html.escape
    # La ficha se hidrata en cliente desde horarios.js; no se congela un
    # cálculo basado en el texto editorial durante la generación estática.
    today = {
        "date_formatted": "Cargando calendario",
        "status_text": "Cargando",
        "status_class": "status-info",
        "today_schedule": "Cargando calendario…",
    }
    horario_inline = d["horario"].replace("\n", " ")
    horario_html = "".join(f"<div>{e(l)}</div>" for l in d["horario"].split("\n"))
    web, web_label = web_url(d)
    desc = f'{d["nombre"]}: {d["direccion"]}. Horario: {horario_inline}. {c["label"]} en Madrid.'
    canonical = BASE + slug
    
    lat, lng = d["lat"], d["lng"]
    photo_url = d.get("foto", "https://bibliotecasmadrid.es/icons/icon-512.png")

    ld = {
        "@context": "https://schema.org",
        "@type": "Library",
        "name": d["nombre"],
        "description": "Horario: " + horario_inline,
        "address": {
            "@type": "PostalAddress",
            "streetAddress": d["direccion"],
            "addressLocality": "Madrid",
        "addressRegion": "Comunidad de Madrid",
            "addressCountry": "ES",
        },
        "geo": {"@type": "GeoCoordinates", "latitude": lat, "longitude": lng},
        "maximumAttendeeCapacity": d.get("plazas", 100),
        "url": canonical,
        "areaServed": "Madrid",
    }
    if d.get("foto"):
        ld["image"] = d["foto"]

    libcal_lid = d.get("libcal_lid")
    libcal_iid = d.get("libcal_iid")
    if libcal_lid and not libcal_iid:
        if "ucm" in d["nombre"].lower() or (d.get("web") and "biblioagenda.ucm.es" in d.get("web")):
            libcal_iid = 4031
        else:
            libcal_iid = 3941

    agenda_name = "BiblioAgenda UCM" if libcal_iid == 4031 else "BiblioAgenda UAM"
    today_api_url = f"https://biblioagenda.ucm.es/api_hours_today.php?iid=4031&lid={libcal_lid}&format=json" if libcal_iid == 4031 else f"https://biblioagenda.uam.es/api_hours_today.php?iid=3941&lid={libcal_lid}&format=json"
    grid_api_url = "https://biblioagenda.ucm.es/api_hours_grid.php?iid=4031&format=json" if libcal_iid == 4031 else "https://biblioagenda.uam.es/api_hours_grid.php?iid=3941&format=json"

    live_tag_html = ""
    week_container_html = '<div id="calendar-week" class="panel-live-week"></div>'

    d_json = json.dumps(d, ensure_ascii=False)
    og_img = d.get("foto", "https://bibliotecasmadrid.es/icons/icon-512.png")

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="theme-color" content="#2563EB">
  <link rel="manifest" href="manifest.json">
  <link rel="apple-touch-icon" href="icons/apple-touch-icon.png">
  <link rel="icon" type="image/png" sizes="64x64" href="icons/favicon-64.png">
  <title>{e(d["nombre"])} · Horario y dirección · Madrid</title>
  <meta name="description" content="{e(desc)}">
  <link rel="canonical" href="{e(canonical)}">
  <meta name="robots" content="index, follow">
  <meta property="og:type" content="article">
  <meta property="og:locale" content="es_ES">
  <meta property="og:title" content="{e(d["nombre"])} · Horario y dirección">
  <meta property="og:description" content="{e(desc)}">
  <meta property="og:url" content="{e(canonical)}">
  <meta property="og:image" content="{e(og_img)}">
  <script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>
  <style>
    :root {{ --ink:#1A1F36; --ink-2:#5A6172; --ink-3:#9AA0AE; --line:#ECEEF2; }}
    * {{ margin:0; padding:0; box-sizing:border-box; }}
    html, body {{
      width:100%; height:100%; overflow:hidden;
      font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;
      -webkit-font-smoothing:antialiased; color:var(--ink);
    }}
    
    /* ── Foto del centro a pantalla completa ── */
    .bg-photo {{
      position: fixed;
      inset: 0;
      width: 100vw;
      height: 100vh;
      z-index: 1;
      background: #0f172a;
    }}
    .bg-photo img {{
      width: 100%;
      height: 100%;
      object-fit: cover;
      display: block;
    }}
    .bg-photo::after {{
      content: '';
      position: absolute;
      inset: 0;
      background: linear-gradient(to top, rgba(0,0,0,0.45) 0%, rgba(0,0,0,0.08) 50%, rgba(0,0,0,0.15) 100%);
      pointer-events: none;
    }}
    
        
    /* ── Tarjeta flotante horizontal centrada abajo ── */
    .card {{
      position: fixed;
      bottom: 24px;
      left: 50%;
      transform: translateX(-50%);
      max-width: 860px;
      width: calc(100% - 48px);
      max-height: calc(100vh - 48px);
      overflow-y: auto;
      background: rgba(255, 255, 255, 0.95);
      backdrop-filter: blur(24px);
      -webkit-backdrop-filter: blur(24px);
      border: 1px solid rgba(255, 255, 255, 0.8);
      border-radius: 24px;
      padding: 22px 28px 20px;
      box-shadow: 0 24px 50px rgba(0,0,0,0.28), 0 4px 12px rgba(0,0,0,0.08);
      z-index: 10;
    }}
    
    .card-header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 12px;
    }}
    .back {{
      display: inline-flex;
      align-items: center;
      gap: 5px;
      font-size: 13px;
      font-weight: 600;
      color: var(--ink-2);
      text-decoration: none;
      transition: color .12s;
    }}
    .back:hover {{ color: var(--ink); }}
    .badge {{
      display: inline-block;
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      padding: 3px 10px;
      border-radius: 999px;
      color: #fff;
      background: {c["fill"]};
    }}
    
    .card-grid {{
      display: grid;
      grid-template-columns: 1.2fr 1fr;
      gap: 28px;
      align-items: start;
    }}
    
    h1 {{
      font-size: 21px;
      font-weight: 800;
      letter-spacing: -0.01em;
      line-height: 1.25;
      margin-bottom: 6px;
    }}
    .addr {{
      font-size: 13.5px;
      color: var(--ink-2);
      line-height: 1.45;
      margin-bottom: 12px;
    }}
    
    .capacity-tag {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      font-size: 12.5px;
      font-weight: 600;
      color: var(--ink-2);
      background: #F1F3F7;
      padding: 6px 12px;
      border-radius: 10px;
      margin-bottom: 16px;
    }}
    .capacity-tag svg {{
      color: var(--ink-3);
      flex-shrink: 0;
    }}

    /* ── Box HOY ───────────────────────────── */
    .today-card {{
      background: #F8FAFC;
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 12px 14px;
      margin-bottom: 12px;
    }}
    .today-head {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 4px;
    }}
    .today-title {{
      font-size: 10.5px;
      font-weight: 800;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--ink-2);
    }}
    .status-badge {{
      display: inline-flex;
      align-items: center;
      gap: 5px;
      font-size: 11.5px;
      font-weight: 700;
      padding: 3px 9px;
      border-radius: 999px;
    }}
    .status-badge.status-open {{
      background: #DCFCE7;
      color: #15803D;
    }}
    .status-badge.status-open::before {{
      content: "";
      display: inline-block;
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background: #16A34A;
    }}
    .status-badge.status-closed {{
      background: #FEE2E2;
      color: #B91C1C;
    }}
    .status-badge.status-closed::before {{
      content: "";
      display: inline-block;
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background: #DC2626;
    }}
    .status-badge.status-info {{
      background: #E0F2FE;
      color: #0369A1;
    }}
    .today-hours {{
      font-size: 13.5px;
      font-weight: 700;
      color: var(--ink);
    }}
    .panel-live-tag {{
      display: inline-flex;
      align-items: center;
      gap: 5px;
      font-size: 10px;
      font-weight: 700;
      color: #0369A1;
      background: #E0F2FE;
      padding: 3px 8px;
      border-radius: 6px;
      margin-top: 6px;
    }}
    .panel-live-tag svg {{
      width: 10px;
      height: 10px;
      fill: #0284C7;
      flex-shrink: 0;
    }}
    .panel-live-week {{
      margin-top: 10px;
      padding-top: 8px;
      border-top: 1px dashed var(--line);
    }}
    .panel-week-table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 11.5px;
      margin-top: 4px;
    }}
    .panel-week-table td {{
      padding: 2.5px 2px;
      color: var(--ink-2);
    }}
    .panel-week-table tr.day-row-today td {{
      font-weight: 700;
      color: #1D4ED8;
    }}
    .panel-week-table td.day-hours {{
      text-align: right;
      font-weight: 600;
      color: var(--ink);
    }}
    .panel-week-table tr.day-row-today td.day-hours {{
      color: #1D4ED8;
    }}

    .sched h2 {{ font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.07em; color: var(--ink-3); margin-bottom: 4px; }}
    .sched {{ font-size:13px; line-height:1.55; border-top:1px solid var(--line); padding-top:10px; }}
    .actions {{ display:flex; flex-wrap:wrap; gap:8px; margin-top:14px; }}
    .btn {{
      display:inline-flex; align-items:center; gap:6px; font-size:12.5px; font-weight:600;
      text-decoration:none; padding:8px 14px; border-radius:999px; transition:filter .12s ease;
    }}
    .btn-primary {{ background:{c["fill"]}; color:#fff; }}
    .btn-primary:hover {{ filter:brightness(1.08); }}
    .btn-ghost {{ background:#F1F3F7; color:var(--ink); }}
    .btn-ghost:hover {{ background:#E7EAF0; }}
    footer {{ margin-top:14px; font-size:10px; color:var(--ink-3); line-height:1.4; }}
    footer a {{ color:var(--ink-3); }}
    
    @media (max-width: 768px) {{
      .card {{
        bottom: 16px;
        padding: 20px 18px 16px;
        width: calc(100% - 32px);
        max-height: 80vh;
      }}
      .card-grid {{
        grid-template-columns: 1fr;
        gap: 16px;
      }}
    }}
  </style>
</head>
<body>
  <!-- Foto del centro a pantalla completa -->
  <div class="bg-photo">
    <img src="{e(photo_url)}" alt="{e(d['nombre'])}" loading="eager">
  </div>
  

  <!-- Tarjeta horizontal centrada abajo -->
  <main class="card">
    <div class="card-header">
      <a class="back" href="./">← Volver al mapa</a>
      <span class="badge">{e(c["label"])}</span>
    </div>
    
    <div class="card-grid">
      <div class="card-main-col">
        <h1>{e(d["nombre"])}</h1>
        <p class="addr">{e(d["distrito"])} · {e(d["direccion"])}</p>
        
        <div class="capacity-tag">
          <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
          <span>{d.get("plazas", 100)} puestos de estudio</span>
        </div>

        <div class="actions">
          <a class="btn btn-primary" href="./#{slug}">Ver en el mapa</a>
          <a class="btn btn-ghost" href="{e(web)}" target="_blank" rel="noopener noreferrer">{e(web_label)} ↗</a>
          <a class="btn btn-ghost" href="https://www.google.com/maps/dir/?api=1&destination={lat},{lng}" target="_blank" rel="noopener noreferrer">Cómo llegar ↗</a>
        </div>
      </div>

      <div class="card-side-col">
        <div class="today-card" id="today-card">
          <div class="today-head">
            <span class="today-title" id="today-title">HOY · {today['date_formatted']}</span>
            <span class="status-badge {today['status_class']}" id="status-badge">{today['status_text']}</span>
          </div>
          <div class="today-hours" id="today-hours">{today['today_schedule']}</div>
          {live_tag_html}
          {week_container_html}
        </div>

        <div class="sched">
          <h2>Horario habitual</h2>
          {horario_html}
        </div>
        
        <footer>
          Datos: <a href="https://datos.madrid.es" target="_blank" rel="noopener">datos.madrid.es</a> (CC BY 4.0).
        </footer>
      </div>
    </div>
  </main>

  <script src="horarios.js"></script>
  <script>
  (function() {{
    const d = {d_json};
    const slug = "{slug}";
    // Interceptar botón 'Atrás' del navegador para ir a "Ver en el mapa"
    try {{
      const mapTarget = './#' + encodeURIComponent(slug);
      if (!history.state || history.state.view !== 'detail') {{
        history.replaceState({{ view: 'map' }}, '', mapTarget);
        history.pushState({{ view: 'detail' }}, '', window.location.href);
      }}
      window.addEventListener('popstate', function(e) {{
        window.location.href = mapTarget;
        window.location.reload();
      }});
    }} catch (err) {{}}
    
    function updateToday() {{
      if (!window.Horarios) return;
      Horarios.renderToday(slug, {{
        title: document.getElementById('today-title'),
        badge: document.getElementById('status-badge'),
        hours: document.getElementById('today-hours')
      }});
    }}
    updateToday();
    const initialWeek = window.Horarios
      ? Horarios.renderWeek(slug, document.getElementById('calendar-week'), 7)
      : Promise.resolve([]);
    setInterval(updateToday, 60000);
    setInterval(() => {{
      if (window.Horarios) Horarios.renderWeek(slug, document.getElementById('calendar-week'), 7);
    }}, 60000);

    if (d.libcal_lid) {{
      function fTime(t) {{
        if (!t) return '';
        const m = t.trim().match(/^(\\d{{1,2}})(?::(\\d{{2}}))?\\s*(am|pm)?$/i);
        if (!m) return t;
        let h = parseInt(m[1], 10);
        const min = m[2] || '00';
        if (m[3] && m[3].toLowerCase() === 'pm' && h < 12) h += 12;
        if (m[3] && m[3].toLowerCase() === 'am' && h === 12) h = 0;
        return h + ':' + min;
      }}

      function updateLiveToday() {{
        return fetch('{today_api_url}')
        .then(r => r.json())
        .then(data => {{
          const loc = (data.locations && data.locations.length > 0) ? data.locations[0] : null;
          if (!loc) return;
          const status = loc.times ? loc.times.status : null;
          const isClosed = status === 'closed' || (status === 'text' && /cerrad/i.test(loc.rendered || loc.times.text || '')) || /cerrad/i.test(loc.rendered || '');
          const badgeEl = document.getElementById('status-badge');
          const hoursEl = document.getElementById('today-hours');
          if (!badgeEl || !hoursEl) return;
          if (isClosed) {{
            badgeEl.className = 'status-badge status-closed';
            badgeEl.textContent = 'Cerrado';
            hoursEl.textContent = 'Cerrado hoy';
          }} else if (status === 'open' && loc.times.hours) {{
            const str = loc.times.hours.map(h => fTime(h.from) + '–' + fTime(h.to) + 'h').join(' y ');
            const isOpen = !!loc.times.currently_open;
            badgeEl.className = 'status-badge ' + (isOpen ? 'status-open' : 'status-closed');
            badgeEl.textContent = isOpen ? 'Abierto' : 'Cerrado';
            hoursEl.textContent = str;
          }}
        }})
        .catch(() => {{}});
      }}
      updateLiveToday();
      setInterval(updateLiveToday, 60000);

      function updateLiveWeek() {{
        const container = document.getElementById('calendar-week');
        if (!container) return;
        fetch('{grid_api_url}')
          .then(r => r.json())
          .then(data => {{
            const loc = (data.locations || []).find(item => Number(item.lid) === Number(d.libcal_lid));
            if (!loc) return;
            const label = container.querySelector('.panel-calendar-week-label');
            if (label) label.textContent = 'Próximos 7 días · En directo ({agenda_name})';
            for (const week of loc.weeks || []) {{
              for (const dayInfo of Object.values(week || {{}})) {{
                if (!dayInfo || !dayInfo.date) continue;
                const row = container.querySelector(`[data-calendar-date="${{dayInfo.date}}"]`);
                const cell = row && row.querySelector('.day-hours');
                if (!cell) continue;
                if (dayInfo.times && dayInfo.times.status === 'open' && dayInfo.times.hours) {{
                  cell.textContent = dayInfo.times.hours.map(hours => fTime(hours.from) + '–' + fTime(hours.to) + 'h').join(' y ');
                }} else if (dayInfo.rendered && !/cerrad/i.test(dayInfo.rendered) && /\d/.test(dayInfo.rendered)) {{
                  cell.textContent = dayInfo.rendered;
                }} else {{
                  cell.textContent = 'Cerrado';
                }}
              }}
            }}
          }})
          .catch(() => {{}});
      }}
      initialWeek.then(updateLiveWeek);
      setInterval(updateLiveWeek, 60000);


    }}
  }})();
  </script>
</body>
</html>
"""


def es_abierto(valor):
    return valor.get("estado") == "abierto" and bool(valor.get("intervalos"))


def es_24_horas(valor):
    return valor.get("estado") == "abierto" and valor.get("intervalos") == [["00:00", "24:00"]]


def texto_intervalos(valor):
    if not valor or valor.get("estado") == "consultar":
        return "Consultar"
    if valor.get("estado") != "abierto":
        return "Cerrado"
    intervalos = valor.get("intervalos") or []
    if intervalos == [["00:00", "24:00"]]:
        return "24 h"
    return " y ".join(f"{inicio}–{fin}h" for inicio, fin in intervalos)


def fechas_24_horas(perfil):
    periodos = []
    for regla in perfil.get("rules", []):
        if es_24_horas(regla) and regla.get("source"):
            periodos.append({
                "from": regla["from"],
                "to": regla["to"],
                "note": regla.get("nota", "Apertura 24 horas"),
                "source": regla["source"],
            })
    return sorted(periodos, key=lambda periodo: (periodo["from"], periodo["to"]))


def abre_algun_fin_de_semana(perfil, calendario):
    year = calendario["year"]
    fecha = dt.date(year, 1, 1)
    ultimo = dt.date(year, 12, 31)
    while fecha <= ultimo:
        if fecha.weekday() in (5, 6) and es_abierto(resolver_dia(perfil, fecha, calendario)):
            return True
        fecha += dt.timedelta(days=1)
    return False


def datos_landing(lugares, slugs, calendario, modo):
    resultado = []
    for lugar, slug in zip(lugares, slugs):
        perfil = calendario["places"][slug]
        periodos = fechas_24_horas(perfil)
        if modo == "weekend" and not abre_algun_fin_de_semana(perfil, calendario):
            continue
        if modo == "full-day" and not periodos:
            continue
        web, _ = web_url(lugar)
        resultado.append({
            "slug": slug,
            "type": lugar["tipo"],
            "typeLabel": COLORES[lugar["tipo"]]["label"],
            "color": COLORES[lugar["tipo"]]["fill"],
            "name": lugar["nombre"],
            "district": lugar.get("distrito", ""),
            "address": lugar["direccion"],
            "lat": lugar["lat"],
            "lng": lugar["lng"],
            "capacity": lugar.get("plazas"),
            "web": web,
            "municipality": perfil["municipio"],
            "weekend": {
                "saturday": perfil["weekly"]["5"],
                "sunday": perfil["weekly"]["6"],
            },
            "periods": periodos,
        })
    return resultado


def ordenar_landing(lugar):
    sabado = es_abierto(lugar["weekend"]["saturday"])
    domingo = es_abierto(lugar["weekend"]["sunday"])
    return (lugar["municipality"] != "madrid", not (sabado and domingo), not domingo, normalizar(lugar["name"]))


def tarjeta_estatica(lugar, modo):
    e = html.escape
    if modo == "weekend":
        detalle = (
            f'<div class="schedule-row"><span>Sábado habitual</span><strong>{e(texto_intervalos(lugar["weekend"]["saturday"]))}</strong></div>'
            f'<div class="schedule-row"><span>Domingo habitual</span><strong>{e(texto_intervalos(lugar["weekend"]["sunday"]))}</strong></div>'
        )
    else:
        detalle = "".join(
            f'<div class="period"><strong>{e(periodo["from"])} — {e(periodo["to"])}</strong>'
            f'<a href="{e(periodo["source"]["url"])}" rel="noopener noreferrer">Fuente oficial</a></div>'
            for periodo in lugar["periods"]
        )
    return f'''<article class="place-card" data-slug="{e(lugar["slug"])}" tabindex="0">
      <div class="card-top"><span class="type-badge" style="--type-color:{e(lugar["color"])}">{e(lugar["typeLabel"])}</span></div>
      <h3>{e(lugar["name"])}</h3>
      <p>{e(lugar["district"])} · {e(lugar["address"])}</p>
      <div class="card-schedule">{detalle}</div>
      <a class="detail-link" href="/{e(lugar["slug"])}">Ver ficha y próximos horarios</a>
    </article>'''


def landing_page_html(lugares, slugs, calendario, modo):
    e = html.escape
    sitios = sorted(datos_landing(lugares, slugs, calendario, modo), key=ordenar_landing)
    year = calendario["year"]
    updated = calendario["last_updated"]
    is_weekend = modo == "weekend"
    route = WEEKEND_ROUTE if is_weekend else FULL_DAY_ROUTE
    title = "Bibliotecas abiertas el fin de semana en Madrid" if is_weekend else "Bibliotecas 24 horas en Madrid: aperturas en época de exámenes"
    description = (
        "Bibliotecas y salas de estudio abiertas los sábados y domingos en Madrid. Consulta horarios actualizados, dirección y mapa para este fin de semana."
        if is_weekend else
        "Bibliotecas y salas de estudio 24 horas en Madrid durante exámenes. Consulta qué centros tienen apertura 24 h confirmada y sus fechas oficiales."
    )
    intro = (
        "Consulta qué bibliotecas y salas de estudio abren el próximo sábado y domingo. Los resultados se actualizan con festivos, verano y excepciones de cada centro."
        if is_weekend else
        "Las aperturas 24 horas no son permanentes: se activan en fechas concretas de exámenes. Aquí solo aparecen periodos confirmados en una fuente oficial."
    )
    capital = [sitio for sitio in sitios if sitio["municipality"] == "madrid"]
    comunidad = [sitio for sitio in sitios if sitio["municipality"] != "madrid"]

    def grupo(titulo_grupo, grupo_sitios):
        if not grupo_sitios:
            return ""
        cards = "\n".join(tarjeta_estatica(sitio, modo) for sitio in grupo_sitios)
        return f'<section class="result-group" data-group="{e(titulo_grupo)}"><h2>{e(titulo_grupo)} <span>{len(grupo_sitios)}</span></h2><div class="cards">{cards}</div></section>'

    if sitios:
        grupos = grupo("Madrid capital", capital) + grupo("Otros municipios", comunidad)
    else:
        grupos = '<div class="empty-state">No hay aperturas 24 horas confirmadas en el calendario vigente. Consulta las opciones de fin de semana.</div>'

    item_list = {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": title,
        "numberOfItems": len(sitios),
        "itemListElement": [
            {"@type": "ListItem", "position": index, "name": sitio["name"], "url": BASE + sitio["slug"]}
            for index, sitio in enumerate(sitios, 1)
        ],
    }
    page_data = json.dumps({
        "mode": modo,
        "route": route,
        "calendarYear": year,
        "calendarUpdated": updated,
        "places": sitios,
    }, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    other_href = f'/{FULL_DAY_ROUTE}' if is_weekend else f'/{WEEKEND_ROUTE}'
    other_label = "Ver bibliotecas 24 horas" if is_weekend else "Ver bibliotecas abiertas el fin de semana"
    filters = '''<div class="filters" id="filters" aria-label="Filtrar por día">
      <button class="active" data-filter="all">Todos</button><button data-filter="saturday">Sábado</button>
      <button data-filter="sunday">Domingo</button><button data-filter="both">Ambos días</button>
    </div>''' if is_weekend else ""
    summary_initial = (
        f"Horarios de fin de semana del calendario {year}. Comprobando las próximas fechas…"
        if is_weekend else
        f"{len(sitios)} centros con periodos 24 h confirmados en el calendario {year}. Comprobando el estado de hoy…"
    )
    canonical = BASE + route
    lastmod = max(LASTMOD, updated)
    return f'''<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="theme-color" content="#2563EB">
  <title>{e(title)}</title>
  <meta name="description" content="{e(description)}">
  <link rel="canonical" href="{e(canonical)}">
  <meta name="robots" content="index, follow">
  <meta property="og:type" content="website"><meta property="og:locale" content="es_ES">
  <meta property="og:title" content="{e(title)}"><meta property="og:description" content="{e(description)}">
  <meta property="og:url" content="{e(canonical)}">
  <script type="application/ld+json">{json.dumps(item_list, ensure_ascii=False)}</script>
  <link rel="manifest" href="manifest.json"><link rel="icon" type="image/png" sizes="64x64" href="icons/favicon-64.png">
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
  <link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css">
  <link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css">
  <link rel="stylesheet" href="seo-landing.css">
</head>
<body>
  <header class="page-header">
    <a class="home-link" href="/">← Volver al mapa</a>
    <h1>{e(title)}</h1><p>{e(intro)}</p>
    <nav class="intent-links" aria-label="Páginas relacionadas"><a href="{other_href}">{other_label}</a></nav>
    <p class="updated">Calendario {year} · revisado el {e(updated)}</p>
  </header>
  <main>
    <section class="map-column" aria-label="Mapa de resultados"><div id="map"></div></section>
    <section class="results-column" aria-live="polite">
      <div class="results-toolbar"><p class="summary" id="summary">{e(summary_initial)}</p>{filters}<div class="notice" id="notice" hidden></div></div>
      <div id="results">{grupos}</div>
    </section>
  </main>
  <aside class="place-panel" id="place-panel" aria-hidden="true"><button id="panel-close" aria-label="Cerrar">×</button><div id="panel-content"></div></aside>
  <noscript><p class="noscript">El listado muestra los horarios habituales o periodos confirmados. Activa JavaScript para comprobar las próximas fechas y usar el mapa.</p></noscript>
  <script>window.LANDING_DATA={page_data};window.LANDING_LASTMOD={json.dumps(lastmod)};</script>
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js"></script>
  <script src="basemap.js"></script>
  <script src="horarios.js"></script><script src="seo-landing.js"></script>
</body>
</html>'''


def sitemap_xml(slugs, calendario=None):
    lastmod_landing = max(LASTMOD, (calendario or {}).get("last_updated", LASTMOD))
    urls = [f"  <url><loc>{BASE}</loc><lastmod>{LASTMOD}</lastmod><changefreq>monthly</changefreq><priority>1.0</priority></url>"]
    urls.extend([
        f"  <url><loc>{BASE}{WEEKEND_ROUTE}</loc><lastmod>{lastmod_landing}</lastmod><changefreq>weekly</changefreq><priority>0.8</priority></url>",
        f"  <url><loc>{BASE}{FULL_DAY_ROUTE}</loc><lastmod>{lastmod_landing}</lastmod><changefreq>weekly</changefreq><priority>0.8</priority></url>",
    ])
    for s in slugs:
        urls.append(
            f"  <url><loc>{BASE}{s}</loc><lastmod>{LASTMOD}</lastmod><changefreq>monthly</changefreq><priority>0.7</priority></url>"
        )
    return '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "\n".join(urls) + "\n</urlset>\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Genera fichas, sitemap y calendarios diarios.")
    parser.add_argument("--migrate-calendar", action="store_true", help="convierte el calendario heredado al schema v2")
    parser.add_argument("--check", action="store_true", help="valida la fuente sin regenerar fichas")
    args = parser.parse_args(argv)

    index_path = os.path.join(ROOT, "index.html")

    print(f"Leyendo {index_path}...")
    lugares = extract_lugares(index_path)
    slugs = unique_slugs(lugares)

    calendario = cargar_calendario()
    if args.migrate_calendar:
        if calendario.get("schema_version") == CALENDAR_SCHEMA_VERSION:
            print("calendario.json ya usa schema_version 2; no se migra de nuevo.")
        else:
            calendario = migrar_calendario(lugares, slugs, calendario)
            with open(CALENDARIO_PATH, "w", encoding="utf-8") as f:
                json.dump(calendario, f, ensure_ascii=False, indent=2)
            print(f"Migrados {len(slugs)} perfiles de calendario a schema v2.")

    errores = validar_calendario(calendario, slugs)
    if errores:
        raise SystemExit("Calendario inválido:\n- " + "\n- ".join(errores))
    if args.check:
        dias = 366 if dt.date(calendario["year"], 12, 31).timetuple().tm_yday == 366 else 365
        print(f"Calendario válido: {len(slugs)} centros y {len(slugs) * dias} días declarados para {calendario['year']}.")
        return

    total_dias = generar_calendarios_publicos(calendario, slugs)

    # 1. Generar HTML por centro
    for d, s in zip(lugares, slugs):
        out_path = os.path.join(ROOT, f"{s}.html")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(page_html(d, s))

    for route, mode in ((WEEKEND_ROUTE, "weekend"), (FULL_DAY_ROUTE, "full-day")):
        out_path = os.path.join(ROOT, f"{route}.html")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(landing_page_html(lugares, slugs, calendario, mode))

    # 2. Generar sitemap.xml
    sitemap_path = os.path.join(ROOT, "sitemap.xml")
    with open(sitemap_path, "w", encoding="utf-8") as f:
        f.write(sitemap_xml(slugs, calendario))

    print(f"Generadas {len(lugares)} fichas + 2 páginas temáticas + sitemap.xml ({len(slugs) + 3} URLs).")
    print(f"Calendario compilado: {total_dias} días en {HORARIOS_DIR}.")
    for s, d in list(zip(slugs, lugares))[:6]:
        print(f"  {s:42s} <- {d['nombre']}")


if __name__ == "__main__":
    main()
