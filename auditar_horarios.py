#!/usr/bin/env python3
"""
auditar_horarios.py - Contrasta el horario de cada centro con su fuente oficial.

Sustituye a sync_madrid.py, que raspaba madrid.es y ya no funciona: Akamai devuelve
403 a cualquier cliente que no sea un navegador de verdad (curl y urllib incluidos).
Este script no raspa: recibe el texto ya extraido y se encarga de lo demas.

Que hace
--------
1. Reconstruye el `#:~:text=` de cada URL oficial a partir del texto REAL de la pagina,
   de modo que el enlace resalte el horario y no caiga al principio del documento.
2. Deriva el perfil semanal (`weekly`), el horario de verano (`rules`) y la politica de
   festivos (`holiday_policy`) del mismo texto, y los compara con `calendario.json`.
3. Avisa de todo lo que no sabe interpretar en vez de escribirlo a ciegas: un horario mal
   deducido es peor que uno sin tocar.
4. Verifica que la URL oficial sigue identica en los dos sitios donde vive:
   `lugares[].web` de index.html y `calendario.json.places[slug].source.url`.

Uso
---
  python auditar_horarios.py --informe                  # audita con lo ya guardado
  python auditar_horarios.py --fuentes fuentes.json     # incorpora texto recien extraido
  python auditar_horarios.py --fuentes fuentes.json --aplicar

`fuentes.json` es `{"<slug>": ["linea 1", "linea 2", ...]}` con el texto del bloque de
horario TAL Y COMO SE VE en la pagina oficial, una entrada por linea de la pagina. Cada
linea es un bloque HTML independiente, que es justo lo que necesita un text fragment:
sus dos extremos tienen que caber cada uno dentro de un mismo bloque.
"""

import argparse
import datetime as dt
import json
import os
import re
import sys
import unicodedata
from urllib.parse import quote

RAIZ = os.path.dirname(os.path.abspath(__file__))
INDEX = os.path.join(RAIZ, "index.html")
CALENDARIO = os.path.join(RAIZ, "calendario.json")

DIAS = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]
LABORABLES = [0, 1, 2, 3, 4]
FIN_DE_SEMANA = [5, 6]

# El fragmento se recorta a un numero de palabras para que la URL no se dispare. Cada
# extremo sigue siendo una subcadena contigua de UNA sola linea, que es lo que exige la
# especificacion de text fragments.
PALABRAS_FRAGMENTO = 12
LARGO_LINEA_ENTERA = 90

# Lineas que son rotulo, no horario.
ROTULOS = re.compile(
    # Un rotulo no lleva cifras: 'Horario de lunes a viernes de 9:00h. a 20:30h.' es el
    # horario en si, no el encabezado que lo precede.
    r"^(horario[^:0-9]*:?\s*$|apertura de |aforo de |en horario de funcionamiento|"
    r"julio y agosto\s*:?\s*$|cerrado\s*:?\s*$|todos los horarios del centro)",
    re.I,
)

# Lineas informativas que no describen cuando abre el centro.
RUIDO = re.compile(
    r"(todos los d[ií]as los servicios|fuera de este horario|puedes contactar|"
    r"por tel[eé]fono|hasta completar aforo|pr[eé]stamo y devoluciones|"
    r"pr[eé]stamo y acceso a internet|"
    r"consulta informaci[oó]n en documentaci[oó]n)",
    re.I,
)

# El horario de OTRO servicio alojado en el mismo edificio. La ficha describe un unico
# centro, asi que mezclarlos daria un horario que no es el de nadie.
OTRO_SERVICIO = re.compile(
    r"^(sala de (estudio|lectura|estudio del centro)|horario de secretar[ií]a|"
    r"horario bibliored|horario pr[eé]stamo)",
    re.I,
)

# Dentro de una misma linea puede colarse el horario de un servicio concreto
# ('Prestamo y acceso a internet: de 9:00 a 20:45 h'), que no es cuando abre el centro.
SERVICIO_SUELTO = re.compile(
    r"^(pr[eé]stamo|devoluciones|acceso a internet|secretar[ií]a|bibliored)\b",
    re.I,
)


# Muchas fichas dan por separado el horario de la sala infantil, mas corto que el del
# centro. Quien busca donde estudiar necesita el general, no el de la sala de niños.
SALA_INFANTIL = re.compile(r"^(sala|secci[oó]n|[aá]rea)?\s*(infantil|juvenil|"
                           r"infantil-juvenil)\b", re.I)


def sin_tildes(texto):
    base = unicodedata.normalize("NFD", texto)
    return "".join(c for c in base if unicodedata.category(c) != "Mn").lower()


# ─────────────────────────────────────────────────────────────────────────────
#  Text fragment
# ─────────────────────────────────────────────────────────────────────────────

def _recorta(linea, desde_el_final):
    """Devuelve una subcadena contigua de `linea`, corta pero inequivoca."""
    if len(linea) <= LARGO_LINEA_ENTERA:
        return linea
    palabras = linea.split()
    trozo = palabras[-PALABRAS_FRAGMENTO:] if desde_el_final else palabras[:PALABRAS_FRAGMENTO]
    return " ".join(trozo)


def construir_fragmento(lineas):
    """`#:~:text=inicio,final` que enmarca las lineas de horario de la pagina.

    Ancla en la primera linea util y cierra en la ultima que lleve una hora, para no
    arrastrar los parrafos de avisos que muchas fichas cuelgan detras.
    """
    # El resaltado tiene que acabar donde acaba el horario del centro: si sigue hasta la
    # ultima hora de la ficha, se come el bloque de la secretaria o de la sala de estudio.
    corte = len(lineas)
    for i, linea in enumerate(lineas):
        if re.search(r"^(horario de secretar[ií]a|horario bibliored|horario pr[eé]stamo|"
                     r"sala de (estudio|lectura))", linea.strip(), re.I):
            corte = i
            break
    lineas = lineas[:corte] or lineas

    utiles = [l for l in lineas if l.strip() and not RUIDO.search(l)]
    if not utiles:
        utiles = [l for l in lineas if l.strip()]
    if not utiles:
        return None
    con_hora = [l for l in utiles if re.search(r"\d{1,2}([:.]\d{2})?\s*(a|-|–)\s*\d", l)]
    inicio = utiles[0]
    final = con_hora[-1] if con_hora else None
    if final is None or final == inicio:
        return "#:~:text=" + quote(_recorta(inicio, False), safe="")
    return "#:~:text=%s,%s" % (
        quote(_recorta(inicio, False), safe=""),
        quote(_recorta(final, True), safe=""),
    )


def fragmento_presente(fragmento, lineas):
    """Comprueba que cada extremo del fragmento existe de verdad en alguna linea."""
    if not fragmento:
        return False
    from urllib.parse import unquote

    partes = [unquote(p) for p in fragmento[len("#:~:text="):].split(",")]
    normalizadas = [re.sub(r"\s+", " ", l).strip().lower() for l in lineas]
    for parte in partes:
        objetivo = re.sub(r"\s+", " ", parte).strip().lower()
        if not any(objetivo in l for l in normalizadas):
            return False
    return True


# ─────────────────────────────────────────────────────────────────────────────
#  Lectura del horario
# ─────────────────────────────────────────────────────────────────────────────

def _construye_rangos():
    """Todas las formas de nombrar dias, de la mas especifica a la mas suelta.

    Se generan en vez de escribirse a mano porque las fichas usan cualquier combinacion
    ('de martes a viernes', 'lunes, miercoles y viernes'), y el que faltaba se leia como
    un dia suelto: 'De martes a viernes' acababa aplicandose solo al viernes.
    """
    nombres = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]
    def como(indice):
        return nombres[indice] + ("s?" if indice >= 5 else "")
    patrones = []
    for i in range(7):                              # de X a Y
        for j in range(6, i, -1):
            patrones.append((r"%s\s+a\s+%s" % (como(i), como(j)), list(range(i, j + 1))))
    patrones.append((r"fines?\s+de\s+semana", FIN_DE_SEMANA))
    for i in range(7):                              # X y Y  /  X, Y
        for j in range(7):
            if i != j:
                patrones.append((r"%s\s*(?:,|y)\s*%s" % (como(i), como(j)), sorted({i, j})))
    for i in range(7):                              # dia suelto
        patrones.append((como(i), [i]))
    return patrones


RANGOS_DIA = _construye_rangos()


def dias_de(texto):
    """Dias de la semana que menciona un fragmento de frase (0 = lunes)."""
    # Las fichas traen erratas de tecleo ('de lunes a a domingo'). Colapsarlas evita que
    # el rango se lea como un dia suelto.
    plano = re.sub(r"\ba(\s+a)+\b", "a", sin_tildes(texto))
    # Erratas vistas en las fuentes oficiales. Sin corregirlas, 'de lunes a viernres' se
    # queda en el lunes.
    plano = re.sub(r"\bviern?r?es\b|\bvienes\b", "viernes", plano)
    plano = re.sub(r"\bdomignos?\b", "domingos", plano)
    for patron, dias in RANGOS_DIA:
        if re.search(patron, plano):
            return list(dias)
    return []


def menciona_festivos(texto):
    return "festivo" in sin_tildes(texto)


def horas_de(texto):
    """Todos los intervalos horarios de una frase, como [["09:00","21:00"], ...]."""
    intervalos = []
    # Los minutos aparecen con dos puntos, punto, coma o apostrofo ("9'00", "9,00"), y a
    # veces la hora lleva pegada una 'h' ("8:30h a 20:45h").
    hora = r"(\d{1,2})(?:[:.,'](\d{2}))?\s*(?:h(?:oras)?)?\.?"
    patron = r"%s\s*(?:a|-|–)\s*%s" % (hora, hora)
    for h1, m1, h2, m2 in re.findall(patron, texto):
        ini_h, fin_h = int(h1), int(h2)
        if ini_h > 24 or fin_h > 24:
            continue
        inicio = "%02d:%02d" % (ini_h, int(m1 or 0))
        # "de 9 a 0 horas" = hasta medianoche.
        fin = "24:00" if fin_h == 0 and not m2 else "%02d:%02d" % (fin_h, int(m2 or 0))
        if inicio >= fin:
            continue
        intervalos.append([inicio, fin])
    return intervalos


DIA_AL_INICIO = (r"(?:de\s+)?(?:lunes|martes|mi[ée]rcoles|jueves|viernes|s[áa]bados?|"
                 r"domingos?|fines?\s+de\s+semana|festivos)")


def trocear(linea):
    """Parte una linea que encadena varios tramos de horario.

    Ademas del punto y el punto y coma, corta en las comas que preceden a un dia de la
    semana ('lunes a viernes de 8:30 a 21, sabado y domingo de 8:30 a 15'): sin eso los
    dos tramos se funden y el sabado acaba heredando el horario del lunes.
    """
    # Algunas fichas pegan el horario de la sala de estudio detras del general sin
    # separador alguno; se marca el limite antes de trocear.
    linea = re.sub(r"\s+(?=Sala de (?:estudio|lectura)\b)", ". ", linea, flags=re.I)
    trozos = []
    # El punto que cierra una hora abreviada ('9:00h. a 20:30h.') no separa dos tramos:
    # partir ahi rompe el intervalo por la mitad.
    for parte in re.split(r"(?<!\dh)[.;]\s+", linea):
        # Corta tanto en la coma como en la 'y' que anteceden a un dia:
        # '...de 9 a 21 h y sabados de 9 a 15 h' son dos tramos, no uno.
        trozos.extend(re.split(r"(?:,|\s+y)\s+(?=%s\b)" % DIA_AL_INICIO, parte, flags=re.I))

    # 'Sabados, domingos y festivos de 9:30 a 20:30' es UNA enumeracion de dias, no dos
    # tramos; y en 'Sabados y domingos. de 08:30 a 15:00' la ficha mete un punto de mas.
    # En ambos casos, un trozo que nombra dias pero no trae horas pertenece al siguiente.
    troceadas, acumulado = [], ""
    for trozo in trozos:
        if not trozo.strip():
            continue
        candidato = (acumulado.rstrip(" .,;") + ", " + trozo) if acumulado else trozo
        if horas_de(trozo) or not dias_de(trozo):
            troceadas.append(candidato)
            acumulado = ""
        else:
            acumulado = candidato
    if acumulado:
        # Un 'de lunes a domingo' que cierra la frase ('de 9:00 a 21:00 h. de lunes a
        # domingo') se refiere al tramo anterior, no abre uno nuevo.
        if troceadas and dias_de(acumulado) and not horas_de(acumulado):
            troceadas[-1] = troceadas[-1].rstrip(" .,;") + ", " + acumulado
        else:
            troceadas.append(acumulado)
    return troceadas


MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6, "jul": 7,
    "ago": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dic": 12,
}
NOMBRE_MES = r"(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre|ene|feb|abr|jun|jul|ago|sept|sep|oct|nov|dic)"
ULTIMO_DIA = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]


def es_verano(texto):
    plano = sin_tildes(texto)
    return bool(re.match(r"^\(?(horario de )?verano\b|^julio\b|^julio y agosto\b", plano))


def es_ampliacion(texto):
    plano = sin_tildes(texto)
    return bool(
        re.search(r"ampliacion horaria|horario ampliado|horario especial examenes|"
                  r"epoca de examenes|campana de apoyo al estudiante|enero-febrero", plano)
    )


def es_cierre(texto):
    plano = sin_tildes(texto)
    return bool(re.search(r"^cerrad|^dias de cierre|cerrad[oa]\.?$|"
                          r"festivos? cerrado|,? cerrad[oa]", plano))


def es_fecha_suelta(texto):
    """'24 y 31 de diciembre, de 10 a 14 horas' -> excepcion de fecha, no semanal."""
    if re.match(r"^\s*(d[ií]as?\s+)?\d{1,2}[\s,y0-9]*de\s+" + NOMBRE_MES, texto, re.I):
        return True
    return bool(re.match(r"^de \d{1,2}(:\d{2})? a \d{1,2}(:\d{2})? horas los d[ií]as", texto, re.I))


def periodo_de(texto, year):
    """Traduce a (desde, hasta) las formas con que se anuncian los periodos estivales.

    Solo acepta rangos EXPLICITOS. Una enumeracion de dias sueltos ('1 y 15 de mayo')
    no es un periodo: darla por buena cerraria el centro un mes entero.
    """
    plano = sin_tildes(texto)
    mes = lambda nombre: MESES[nombre]
    mes_completo = lambda n: (dt.date(year, n, 1), dt.date(year, n, ULTIMO_DIA[n - 1]))

    m = re.search(r"del?\s+(\d{1,2})\s+de\s+(\w+)\s+al?\s+(\d{1,2})\s+de\s+(\w+)", plano)
    if m and m.group(2) in MESES and m.group(4) in MESES:
        return (dt.date(year, mes(m.group(2)), int(m.group(1))),
                dt.date(year, mes(m.group(4)), int(m.group(3))))

    m = re.search(r"\(?(\d{1,2})\s+(\w+)\s+a\s+(\d{1,2})\s+(\w+)\)?", plano)
    if m and m.group(2) in MESES and m.group(4) in MESES:
        return (dt.date(year, mes(m.group(2)), int(m.group(1))),
                dt.date(year, mes(m.group(4)), int(m.group(3))))

    m = re.search(r"del?\s+(\d{1,2})\s+al\s+(\d{1,2})\s+(?:de\s+)?(\w+)", plano)
    if m and m.group(3) in MESES:
        return (dt.date(year, mes(m.group(3)), int(m.group(1))),
                dt.date(year, mes(m.group(3)), int(m.group(2))))

    m = re.search(r"tres primeras semanas de (\w+)", plano)
    if m and m.group(1) in MESES:
        return dt.date(year, mes(m.group(1)), 1), dt.date(year, mes(m.group(1)), 21)

    m = re.search(r"de (%s) a (%s)" % (NOMBRE_MES, NOMBRE_MES), plano)
    if m:
        fin = mes(m.group(2))
        return dt.date(year, mes(m.group(1)), 1), dt.date(year, fin, ULTIMO_DIA[fin - 1])

    # A partir de aqui basta con nombrar el mes ('y agosto cerrado', 'Julio y Agosto:').
    # Solo vale si la frase NO enumera dias concretos: en 'Cerrado: 1 de enero, 6 de
    # enero y 25 de diciembre' el mes aparece por la fecha, y tomarlo como periodo
    # cerraria enero entero.
    if re.search(r"\d{1,2}\s+(?:y\s+\d{1,2}\s+)?de\s+" + NOMBRE_MES, plano):
        return None

    m = re.search(r"\b(%s)(?:\s*,\s*(%s))?(?:\s+y\s+(%s))?\b"
                  % (NOMBRE_MES, NOMBRE_MES, NOMBRE_MES), plano)
    if m:
        nombrados = [g for g in m.groups() if g in MESES]
        if nombrados:
            primero, ultimo = mes(nombrados[0]), mes(nombrados[-1])
            if primero <= ultimo:
                return dt.date(year, primero, 1), mes_completo(ultimo)[1]
    return None


def dias_cerrados(texto):
    """Dias de la semana que una frase de cierre deja cerrados TODA la temporada.

    Distingue el cierre semanal ('Domingos, festivos y agosto cerrado') de la lista de
    fechas sueltas ('Dias de cierre: sabados: 4 de abril, 16 de mayo...'), que no cierra
    los sabados: solo esos sabados concretos.
    """
    cuerpo = re.sub(r"^\s*(d[ií]as de cierre|cerrad[oa]s?(\s+los\s+d[ií]as)?)\s*"
                    r"(\([^)]*\))?\s*:?\s*", "", texto, flags=re.I)
    # Los parentesis aclaran un periodo ('Semana Santa (de jueves a domingo)'), no
    # anuncian un cierre semanal.
    cuerpo = re.sub(r"\([^)]*\)", " ", cuerpo)
    dias = set()
    for trozo in re.split(r"[;.,]", cuerpo):
        if re.search(r"\d", trozo):
            continue
        if re.search(NOMBRE_MES, sin_tildes(trozo)):
            continue
        if re.search(r"semana santa|navidad|pascua", sin_tildes(trozo)):
            continue
        dias.update(dias_de(trozo))
    for m in re.finditer(r"(lunes|martes|mi[ée]rcoles|jueves|viernes|s[áa]bados?|domingos?)"
                         r"\s*:?\s*todos", texto, re.I):
        dias.update(dias_de(m.group(1)))
    return dias


ABREVIATURAS_DIA = {"l": 0, "m": 1, "x": 2, "j": 3, "v": 4, "s": 5, "d": 6}


def resolver_apertura(lineas):
    """A que dias se aplica un horario que no los nombra.

    Lo declara o bien un 'Apertura de lunes a viernes.' al principio de la ficha, o bien
    el encabezado de una tabla ('Horario L-V'), que es como lo publican las
    universidades.
    """
    for linea in lineas:
        plano = sin_tildes(linea)
        if plano.startswith("apertura de"):
            return dias_de(linea)
        cabecera = re.match(r"^horario\s+([lmxjvsd])\s*-\s*([lmxjvsd])$", plano)
        if cabecera:
            desde = ABREVIATURAS_DIA[cabecera.group(1)]
            hasta = ABREVIATURAS_DIA[cabecera.group(2)]
            if desde <= hasta:
                return list(range(desde, hasta + 1))
    return None


def construir_weekly(lineas, year=2026):
    """Deriva (weekly, reglas de verano, holiday_policy, avisos) del texto oficial."""
    avisos = []
    semanal = {}
    generico = None
    verano = []           # (dias|None, intervalos|None, periodo|None, es_cierre)
    abre_festivos = None
    cierra_dias = set()
    contexto_examenes = False
    contexto_otro = False
    rotulo_verano = None

    for linea in lineas:
        limpia = re.sub(r"\s+", " ", linea).strip()
        if not limpia:
            continue
        if ROTULOS.match(limpia):
            # Un rotulo tiñe las lineas que cuelgan debajo: ni el rango de examenes, ni
            # el 'Julio y Agosto:', ni el 'Horario de secretaria:' se repiten linea a
            # linea. Sin arrastrar ese contexto, el horario de la secretaria acaba
            # publicado como el horario del centro.
            contexto_examenes = bool(re.search(r"ex[aá]menes|campa[ñn]a", limpia, re.I))
            contexto_otro = bool(re.search(r"secretar[ií]a|bibliored|pr[eé]stamo|"
                                           r"sala de (estudio|lectura)", limpia, re.I))
            rotulo_verano = limpia if es_verano(limpia) else None
            continue
        if contexto_otro:
            avisos.append("horario de otro servicio del edificio, ignorado: " + limpia[:60])
            continue
        if RUIDO.search(limpia) and not horas_de(limpia):
            continue
        if OTRO_SERVICIO.match(limpia):
            avisos.append("horario de otro servicio del edificio, ignorado: " + limpia[:60])
            continue
        if es_ampliacion(limpia) or contexto_examenes:
            avisos.append("ampliacion horaria sin automatizar: " + limpia[:60])
            continue
        if es_fecha_suelta(limpia) or re.match(r"^horario especial", limpia, re.I):
            continue

        contexto_verano = es_verano(limpia) or rotulo_verano is not None
        periodo_linea = None
        if contexto_verano:
            periodo_linea = periodo_de(limpia, year)
            if not periodo_linea and rotulo_verano:
                periodo_linea = periodo_de(rotulo_verano, year)
        interpretada = False

        arrastra_verano = False
        periodo_arrastrado = None
        ultimos_dias = None
        for tramo in trocear(limpia):
            # 'lunes a viernes de 8:30 a 21. Verano (...): lunes a viernes de 8:30 a 20,
            # sabado y domingo de 8:30 a 14' -> el 'Verano' del tercer tramo tambien manda
            # sobre el cuarto; sin arrastrarlo, el sabado de verano pisa al de todo el año.
            if es_verano(tramo):
                arrastra_verano = True
                periodo_arrastrado = periodo_de(tramo, year) or periodo_arrastrado
            veraniega = contexto_verano or arrastra_verano
            cuerpo = re.sub(r"^\(?(horario de )?verano[^:]*:\s*", "", tramo, flags=re.I)
            cuerpo = re.sub(r"^julio y agosto\s*:\s*", "", cuerpo, flags=re.I)
            horas = horas_de(cuerpo)

            if es_cierre(tramo) and not horas:
                interpretada = True
                if menciona_festivos(tramo) and abre_festivos is None and not veraniega:
                    abre_festivos = False
                if not veraniega:
                    cierra_dias.update(dias_cerrados(tramo))
                periodo = periodo_de(tramo, year)
                if not periodo and veraniega:
                    periodo = periodo_linea or periodo_arrastrado
                if periodo:
                    verano.append((dias_de(tramo) or None, None, periodo, True))
                continue

            if not horas:
                continue
            if OTRO_SERVICIO.match(cuerpo.strip()) or SERVICIO_SUELTO.search(cuerpo):
                avisos.append("horario de otro servicio del edificio, ignorado: " + cuerpo[:60])
                interpretada = True
                continue
            if SALA_INFANTIL.match(cuerpo.strip()):
                interpretada = True
                continue
            interpretada = True
            dias = dias_de(cuerpo) or None
            festivos = menciona_festivos(cuerpo)
            if festivos and abre_festivos is None:
                abre_festivos = True

            # 'De lunes a viernes de 10 a 14:30 h. y de 16:30 a 21 h.': el segundo tramo
            # no repite los dias porque son los mismos. Es la jornada partida, no un
            # horario generico.
            continuacion = dias is None and not festivos and ultimos_dias is not None
            if dias:
                ultimos_dias = list(dias)

            if veraniega:
                verano.append((dias or (ultimos_dias if continuacion else None), horas,
                               periodo_de(tramo, year) or periodo_linea or periodo_arrastrado,
                               False))
            elif continuacion:
                for dia in ultimos_dias:
                    semanal[dia] = semanal.get(dia, []) + horas
            elif dias is None:
                # 'Festivos, de 10 a 13:50 horas' habla de los festivos, no de la semana:
                # tomarlo por horario generico machacaria los dias ya leidos.
                if not festivos:
                    generico = horas
            else:
                for dia in dias:
                    semanal[dia] = horas

        # Una linea sin cifras es un rotulo ('Bib. ETSI Caminos...'), no un horario que
        # se haya escapado: no merece aviso.
        if not interpretada and re.search(r"\d", limpia):
            avisos.append("linea sin interpretar: " + limpia[:60])

    if generico is not None:
        dias = resolver_apertura(lineas)
        if not dias:
            avisos.append("horario generico sin dias de apertura declarados")
            dias = LABORABLES
        for dia in dias:
            semanal.setdefault(dia, generico)

    weekly = {}
    if not semanal:
        # La ficha oficial no publica horario ('Consultar telefonicamente'). Decirlo es
        # mas honesto que inventar una semana.
        avisos.append("la fuente oficial no publica horario: queda en 'consultar'")
        for dia in range(7):
            weekly[str(dia)] = {"estado": "consultar", "intervalos": [],
                                "nota": "Horario no publicado en la fuente oficial"}
        return weekly, [], abre_festivos, avisos

    for dia in range(7):
        if dia in semanal and dia not in cierra_dias:
            weekly[str(dia)] = {
                "estado": "abierto",
                "intervalos": semanal[dia],
                "nota": "Horario habitual",
            }
        else:
            weekly[str(dia)] = {
                "estado": "cerrado",
                "intervalos": [],
                "nota": "Cerrado según horario habitual",
            }

    reglas, mas_avisos = construir_reglas(verano, weekly, lineas, year)
    return weekly, reglas, abre_festivos, avisos + mas_avisos


NOTAS_TEMPORADA = {
    "Horario de verano", "Cerrado en horario de verano", "Cierre de verano",
    "Cierre de agosto", "Horario reducido de agosto",
}


def construir_reglas(verano, weekly, lineas, year):
    """Convierte lo leido sobre el verano en reglas con fechas concretas."""
    reglas, avisos = [], []
    abiertos = [d for d in range(7) if weekly[str(d)]["estado"] == "abierto"]

    for dias, horas, periodo, cierra in verano:
        if not periodo:
            avisos.append("periodo estival sin fechas reconocibles")
            continue
        desde, hasta = periodo
        base = {"from": desde.isoformat(), "to": hasta.isoformat()}
        if cierra:
            regla = dict(base, estado="cerrado", intervalos=[], priority=70,
                         nota="Cierre de verano")
            if dias:
                regla["weekdays"] = sorted(dias)
            reglas.append(regla)
            continue
        aplicables = sorted(set(dias) & set(abiertos)) if dias else abiertos
        if not aplicables:
            avisos.append("horario de verano para dias que la semana da por cerrados")
            continue
        reglas.append(dict(base, estado="abierto", intervalos=horas, priority=60,
                           weekdays=aplicables, nota="Horario de verano"))

    if not reglas:
        for linea in lineas:
            if re.search(r"\bveran|^julio\b|^julio y agosto\b", sin_tildes(linea)) \
                    and not es_ampliacion(linea) and not es_fecha_suelta(linea):
                avisos.append("menciona el verano pero no se ha derivado ninguna regla")
                break
    return reglas, avisos


# ─────────────────────────────────────────────────────────────────────────────
#  index.html / calendario.json
# ─────────────────────────────────────────────────────────────────────────────

def cargar_build():
    import importlib.util

    spec = importlib.util.spec_from_file_location("build", os.path.join(RAIZ, "build.py"))
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def resumen_weekly(weekly):
    partes = []
    for dia in range(7):
        entrada = weekly[str(dia)]
        if entrada["estado"] != "abierto":
            continue
        horas = " y ".join("%s-%s" % (a, b) for a, b in entrada["intervalos"])
        partes.append("%s %s" % (DIAS[dia][:3].capitalize(), horas))
    return " · ".join(partes) or "cerrado toda la semana"


ETIQUETAS_DIA = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]


def _hora_corta(valor):
    """'09:00' -> '9'; '08:30' -> '8:30', que es como se escribe en las fichas."""
    horas, minutos = valor.split(":")
    return str(int(horas)) if minutos == "00" else "%d:%s" % (int(horas), minutos)


def texto_horario(weekly, holiday_policy, original=""):
    """Reescribe el `horario` editorial de index.html a partir del semanal verificado.

    Este texto es el que se ve como 'Horario habitual' junto a la tabla de 7 dias: si no
    se regenera, sigue anunciando el horario viejo justo al lado del corregido. Se
    respeta el estilo existente ('Lun–Vie 9–21h · Sáb 9–14h') y se conservan las lineas
    extra del original, que llevan matices que el calendario no recoge (exámenes).
    """
    grupos = []
    for dia in range(7):
        entrada = weekly[str(dia)]
        if entrada["estado"] != "abierto":
            continue
        horas = " y ".join("%s–%sh" % (_hora_corta(a), _hora_corta(b))
                           for a, b in entrada["intervalos"])
        if grupos and grupos[-1][2] == horas and grupos[-1][1] == dia - 1:
            grupos[-1][1] = dia
        else:
            grupos.append([dia, dia, horas])

    if not grupos:
        primera = "Consultar horario"
    else:
        toda_la_semana = len(grupos) == 1 and grupos[0][:2] == [0, 6]
        partes = []
        for desde, hasta, horas in grupos:
            dias = ETIQUETAS_DIA[desde] if desde == hasta else "%s–%s" % (
                ETIQUETAS_DIA[desde], ETIQUETAS_DIA[hasta])
            # 'Lun–Dom y festivos 9–22h': si el centro abre tambien en festivo, decirlo
            # aqui evita que el texto parezca mas restrictivo que el calendario.
            if toda_la_semana and holiday_policy == "open":
                dias += " y festivos"
            partes.append("%s %s" % (dias, horas))
        primera = " · ".join(partes)
        if holiday_policy == "closed" and toda_la_semana:
            primera += " (festivos cerrado)"

    resto = original.split("\n")[1:]
    return "\n".join([primera] + resto)


def sustituir_horario(fuente, nombre, texto_viejo, texto_nuevo):
    """Cambia el `horario:` del centro `nombre` en index.html."""
    if texto_viejo == texto_nuevo:
        return fuente, False
    marca = 'nombre: "%s"' % nombre
    lineas = fuente.split("\n")
    indices = [i for i, l in enumerate(lineas) if marca in l]
    if len(indices) != 1:
        raise ValueError("en index.html hay %d lineas para %s" % (len(indices), nombre))
    i = indices[0]
    # En el fuente el salto de linea va escapado como \n dentro de la cadena JS.
    escapado = texto_nuevo.replace("\n", "\\n")
    nueva, cuantas = re.subn(r'horario: "[^"]*"',
                             lambda _: 'horario: "%s"' % escapado, lineas[i])
    if cuantas != 1:
        raise ValueError("no hay un unico horario: en la linea de " + nombre)
    lineas[i] = nueva
    return "\n".join(lineas), True


def resumen_reglas(reglas):
    if not reglas:
        return "(ninguna)"
    partes = []
    for regla in reglas:
        horas = " y ".join("%s-%s" % (a, b) for a, b in regla.get("intervalos") or []) or "cerrado"
        dias = regla.get("weekdays")
        etiqueta = "" if dias is None else " [%s]" % ",".join(DIAS[d][:3] for d in dias)
        partes.append("%s→%s %s%s" % (regla["from"][5:], regla["to"][5:], horas, etiqueta))
    return " | ".join(partes)


def sustituir_web(fuente, nombre, url_vieja, url_nueva):
    """Cambia el `web:` del centro `nombre` en index.html.

    Se localiza por nombre y no por URL: varios centros de un mismo municipio comparten
    la misma URL oficial, asi que sustituir por URL cambiaria el primero que aparezca.
    """
    if url_vieja == url_nueva:
        return fuente, False
    marca = 'nombre: "%s"' % nombre
    lineas = fuente.split("\n")
    indices = [i for i, l in enumerate(lineas) if marca in l]
    if len(indices) != 1:
        raise ValueError("en index.html hay %d lineas para %s" % (len(indices), nombre))
    i = indices[0]
    nueva, cuantas = re.subn(r'web: "[^"]*"', lambda _: 'web: "%s"' % url_nueva, lineas[i])
    if cuantas != 1:
        raise ValueError("no hay un unico web: en la linea de " + nombre)
    lineas[i] = nueva
    return "\n".join(lineas), True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fuentes", action="append",
                        help="JSON {slug: [lineas]} o {slug: {url, lineas}}. Repetible.")
    parser.add_argument("--aplicar", action="store_true", help="escribe los cambios")
    parser.add_argument("--informe", action="store_true", help="vuelca la comparacion")
    parser.add_argument("--solo", help="limita a un slug")
    args = parser.parse_args()

    build = cargar_build()
    lugares = build.extract_lugares(INDEX)
    slugs = build.unique_slugs(lugares)
    por_slug = dict(zip(slugs, lugares))

    with open(CALENDARIO, encoding="utf-8") as f:
        calendario = json.load(f)
    perfiles = calendario["places"]

    # Una fuente es la lista de lineas del horario oficial. Si ademas cambia la URL del
    # centro (porque la que habia estaba muerta), se pasa como {"url":..., "lineas":[...]}.
    fuentes, urls_nuevas, sin_fragmento, solo_url = {}, {}, set(), set()
    for ruta in args.fuentes or []:
        with open(ruta, encoding="utf-8") as f:
            for slug, valor in json.load(f).items():
                if isinstance(valor, dict):
                    fuentes[slug] = valor["lineas"]
                    if valor.get("url"):
                        urls_nuevas[slug] = valor["url"]
                    if valor.get("fragmento") is False:
                        sin_fragmento.add(slug)
                    if valor.get("solo_url"):
                        solo_url.add(slug)
                else:
                    fuentes[slug] = valor
    for slug, perfil in perfiles.items():
        texto = (perfil.get("source") or {}).get("texto")
        if texto and slug not in fuentes:
            fuentes[slug] = texto

    fuente_index = open(INDEX, encoding="utf-8").read()
    hoy = dt.date.today().isoformat()
    cambios_url = cambios_weekly = cambios_texto = 0
    problemas = []

    for slug in slugs:
        if args.solo and slug != args.solo:
            continue
        lugar = por_slug[slug]
        perfil = perfiles.get(slug)
        if perfil is None:
            problemas.append("%s: sin perfil en calendario.json" % slug)
            continue

        web_actual = lugar.get("web", "")
        fuente_url = (perfil.get("source") or {}).get("url", "")
        if web_actual != fuente_url:
            problemas.append("%s: index.html y calendario.json apuntan a URLs distintas" % slug)

        lineas = fuentes.get(slug)
        if not lineas:
            problemas.append("%s: sin texto oficial verificado" % slug)
            # Sin texto que respalde el ancla, el fragmento es una conjetura: el enlace
            # no resalta nada y ademas deja la URL con basura. Mejor quitarlo y que al
            # menos abra limpia la pagina oficial.
            if "#:~:text=" in web_actual:
                limpia = web_actual.split("#:~:text=")[0]
                problemas.append("%s: fragmento sin verificar eliminado" % slug)
                if args.aplicar:
                    fuente_index, _ = sustituir_web(fuente_index, lugar["nombre"],
                                                    web_actual, limpia)
                    perfil.setdefault("source", {})["url"] = limpia
                    cambios_url += 1
            continue

        base = urls_nuevas.get(slug, web_actual).split("#:~:text=")[0]
        if slug in sin_fragmento:
            # Hay centros cuyo horario lo pinta JavaScript (LibCal). Ahi no existe texto
            # al que anclar: es preferible un enlace limpio a la pagina del horario que
            # un fragmento que nunca va a resaltar nada.
            fragmento = None
        else:
            fragmento = construir_fragmento(lineas)
            if not fragmento_presente(fragmento, lineas):
                problemas.append("%s: el fragmento no existe en el texto oficial" % slug)
                fragmento = None
        nueva_url = base + (fragmento or "")

        if slug in solo_url:
            # El horario que ve el usuario viene en vivo de la API del centro, asi que el
            # semanal de respaldo se deja como esta y solo se corrige el enlace.
            weekly, reglas, abre_festivos, avisos = perfil["weekly"], [], None, []
        else:
            weekly, reglas, abre_festivos, avisos = construir_weekly(lineas, calendario["year"])
        for aviso in avisos:
            problemas.append("%s: %s" % (slug, aviso))

        antes = resumen_weekly(perfil["weekly"])
        ahora = resumen_weekly(weekly)
        reglas_antes = [r for r in perfil.get("rules", []) if r.get("nota") in NOTAS_TEMPORADA]
        if args.informe:
            marca = "  " if antes == ahora else "!!"
            print("%s %s" % (marca, slug))
            for linea in lineas:
                print("      · %s" % linea[:150])
            print("      calendario: %s" % antes)
            print("      oficial   : %s" % ahora)
            if reglas_antes or reglas:
                print("      verano antes : %s" % resumen_reglas(reglas_antes))
                print("      verano ahora : %s" % resumen_reglas(reglas))
            if avisos:
                print("      avisos    : %s" % "; ".join(avisos))
            print()

        politica = perfil.get("holiday_policy")
        if abre_festivos is True:
            politica = "open"
        elif abre_festivos is False:
            politica = "closed"
        horario_nuevo = texto_horario(weekly, politica, lugar.get("horario", ""))

        if args.informe and horario_nuevo != lugar.get("horario", ""):
            print("      texto antes: %s" % lugar.get("horario", "").replace("\n", " / "))
            print("      texto ahora: %s" % horario_nuevo.replace("\n", " / "))

        if args.aplicar:
            fuente_index, cambio = sustituir_web(fuente_index, lugar["nombre"], web_actual, nueva_url)
            cambios_url += cambio
            fuente_index, cambio_texto = sustituir_horario(
                fuente_index, lugar["nombre"], lugar.get("horario", ""), horario_nuevo)
            cambios_texto += cambio_texto
            if antes != ahora:
                perfil["weekly"] = weekly
                cambios_weekly += 1
            if reglas:
                # Las reglas de examenes las fija la fuente del propio centro, no este
                # texto: se conservan tal cual y solo se reemplazan las de temporada.
                otras = [r for r in perfil.get("rules", []) if r.get("nota") not in NOTAS_TEMPORADA]
                perfil["rules"] = reglas + otras
            fuente = perfil.setdefault("source", {})
            fuente["url"] = nueva_url
            fuente["checked_at"] = hoy
            # No todo lo que dice una ficha oficial se deja convertir en calendario. Si
            # ha quedado algun cabo suelto, la etiqueta lo dice en vez de aparentar que
            # el perfil entero esta contrastado.
            fuente["confidence"] = ("verificado-en-fuente-oficial" if not avisos
                                    else "verificado-con-reservas")
            if avisos:
                fuente["reservas"] = avisos
            else:
                fuente.pop("reservas", None)
            fuente["texto"] = lineas
            if abre_festivos is True:
                perfil["holiday_policy"] = "open"
            elif abre_festivos is False:
                perfil["holiday_policy"] = "closed"

    if args.aplicar:
        with open(INDEX, "w", encoding="utf-8") as f:
            f.write(fuente_index)
        calendario["last_updated"] = hoy
        with open(CALENDARIO, "w", encoding="utf-8") as f:
            json.dump(calendario, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print("URLs actualizadas: %d · perfiles semanales corregidos: %d · textos de horario reescritos: %d" % (cambios_url, cambios_weekly, cambios_texto))

    if problemas:
        print("\n--- %d avisos ---" % len(problemas))
        for p in problemas:
            print("  " + p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
