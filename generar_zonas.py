"""Genera zonas-madrid.geojson desde cartografia oficial.

El fichero generado es el que consume el buscador del mapa. Reune:

* barrios y distritos del Geoportal del Ayuntamiento de Madrid;
* los 179 municipios de la Comunidad de Madrid del WFS INSPIRE del IGN-CNIG.

Las geometrías se simplifican lo justo para web. Las fuentes originales siguen siendo
la autoridad: este script solo cambia el formato y reduce puntos redundantes.
"""

from __future__ import annotations

import json
import math
import os
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date


ROOT = os.path.dirname(os.path.abspath(__file__))
OUTPUT = os.path.join(ROOT, "zonas-madrid.geojson")

BARRIOS_URL = (
    "https://geoportal.madrid.es/fsdescargas/IDEAM_WBGEOPORTAL/"
    "LIMITES_ADMINISTRATIVOS/Barrios/TopoJSON/Barrios.json"
)
DISTRITOS_URL = (
    "https://geoportal.madrid.es/fsdescargas/IDEAM_WBGEOPORTAL/"
    "LIMITES_ADMINISTRATIVOS/Distritos/TopoJSON/Distritos.json"
)
IGN_WFS_URL = "https://contenido.ign.es/wfs-inspire/unidades-administrativas"

# Los nombres populares no siempre coinciden con los 131 barrios administrativos. Se
# conservan como alias de búsqueda; el mapa deja claro cuál es el barrio oficial que se
# está resaltando.
BARRIO_ALIASES = {
    "Palacio": ["Madrid de los Austrias", "La Latina"],
    "Embajadores": ["Lavapiés", "El Rastro"],
    "Cortes": ["Barrio de las Letras", "Las Letras", "Huertas"],
    "Justicia": ["Chueca"],
    "Universidad": ["Malasaña", "Maravillas", "Conde Duque"],
    "Sol": ["Callao"],
    "Los Jerónimos": ["Jerónimos"],
    "Recoletos": ["Milla de Oro"],
    "Legazpi": ["Matadero"],
    "Atocha": ["Méndez Álvaro"],
    "Cuatro Caminos": ["AZCA"],
    "Castillejos": ["Cuzco"],
    "Hispanoamérica": ["Bernabéu"],
    "Bellas Vistas": ["Estrecho"],
    "Valdeacederas": ["Ventilla"],
    "Valverde": ["Las Tablas", "Tres Olivos"],
    "El Goloso": ["Montecarmelo"],
    "Valdefuentes": ["Sanchinarro", "Las Cárcavas"],
    "Timón": ["Valdebebas"],
    "Apóstol Santiago": ["Manoteras"],
    "Alameda de Osuna": ["El Capricho"],
    "Casa de Campo": ["Batán"],
    "Acacias": ["Pirámides"],
    "Simancas": ["Julián Camarillo"],
    "Rejas": ["Plenilunio"],
}

NS = {
    "wfs": "http://www.opengis.net/wfs/2.0",
    "au": "http://inspire.ec.europa.eu/schemas/au/4.0",
    "gml": "http://www.opengis.net/gml/3.2",
    "gn": "http://inspire.ec.europa.eu/schemas/gn/4.0",
}


def download_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": "DondeEstudioHoy/1.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def download_municipios() -> bytes:
    # 34 = España, 13 = Comunidad de Madrid, 28 = provincia de Madrid. Los cinco
    # últimos dígitos son el municipio; el patrón devuelve exactamente 179 unidades.
    filtro = """<fes:Filter xmlns:fes="http://www.opengis.net/fes/2.0">
      <fes:PropertyIsLike wildCard="*" singleChar="?" escapeChar="!">
        <fes:ValueReference>nationalCode</fes:ValueReference>
        <fes:Literal>34132828*</fes:Literal>
      </fes:PropertyIsLike>
    </fes:Filter>"""
    params = urllib.parse.urlencode({
        "SERVICE": "WFS",
        "VERSION": "2.0.0",
        "REQUEST": "GetFeature",
        "TYPENAMES": "au:AdministrativeUnit",
        "SRSNAME": "urn:ogc:def:crs:EPSG::4326",
        "FILTER": filtro,
    })
    request = urllib.request.Request(
        f"{IGN_WFS_URL}?{params}", headers={"User-Agent": "DondeEstudioHoy/1.0"}
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def point_segment_distance(point, start, end):
    px, py = point
    ax, ay = start
    bx, by = end
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def simplify_line(points, tolerance):
    if len(points) <= 2:
        return points
    start, end = points[0], points[-1]
    distance, split = 0.0, 0
    for index, point in enumerate(points[1:-1], 1):
        candidate = point_segment_distance(point, start, end)
        if candidate > distance:
            distance, split = candidate, index
    if distance <= tolerance:
        return [start, end]
    left = simplify_line(points[: split + 1], tolerance)
    right = simplify_line(points[split:], tolerance)
    return left[:-1] + right


def simplify_ring(ring, tolerance):
    points = ring[:-1] if ring and ring[0] == ring[-1] else list(ring)
    if len(points) <= 4:
        return points + [points[0]]

    # RDP necesita extremos distintos. Se parte el anillo por sus extremos oeste/este,
    # simplificando las dos mitades sin abrir huecos en el cierre.
    west = min(range(len(points)), key=lambda i: (points[i][0], points[i][1]))
    east = max(range(len(points)), key=lambda i: (points[i][0], points[i][1]))
    if west == east:
        return points + [points[0]]
    if west > east:
        west, east = east, west
    first = simplify_line(points[west : east + 1], tolerance)
    second = simplify_line(points[east:] + points[: west + 1], tolerance)
    simplified = first[:-1] + second[:-1]
    if len(simplified) < 3:
        simplified = points
    return simplified + [simplified[0]]


def decode_topology(topology):
    scale_x, scale_y = topology["transform"]["scale"]
    translate_x, translate_y = topology["transform"]["translate"]
    decoded = []
    for encoded_arc in topology["arcs"]:
        x = y = 0
        arc = []
        for dx, dy in encoded_arc:
            x += dx
            y += dy
            arc.append([x * scale_x + translate_x, y * scale_y + translate_y])
        decoded.append(simplify_line(arc, 0.00008))
    return decoded


def join_arcs(indices, arcs):
    ring = []
    for raw_index in indices:
        arc = arcs[raw_index] if raw_index >= 0 else list(reversed(arcs[~raw_index]))
        ring.extend(arc if not ring else arc[1:])
    if ring and ring[0] != ring[-1]:
        ring.append(ring[0])
    return [[round(x, 6), round(y, 6)] for x, y in ring]


def topo_features(topology, object_name, kind):
    arcs = decode_topology(topology)
    features = []
    for geometry in topology["objects"][object_name]["geometries"]:
        properties = geometry["properties"]
        name = properties["NOMBRE"].strip()
        rings = [join_arcs(indices, arcs) for indices in geometry["arcs"]]
        feature_properties = {
            "nombre": name,
            "tipo": kind,
            "contexto": (
                f"Distrito {properties['NOMDIS'].strip()} · Madrid"
                if kind == "barrio"
                else "Madrid"
            ),
        }
        aliases = BARRIO_ALIASES.get(name)
        if aliases:
            feature_properties["aliases"] = aliases
        features.append({
            "type": "Feature",
            "id": f"{kind}-{properties.get('COD_BAR') or properties.get('COD_DIS_TX')}",
            "properties": feature_properties,
            "geometry": {"type": "Polygon", "coordinates": rings},
        })
    return features


def parse_pos_list(element):
    values = [float(value) for value in (element.text or "").split()]
    # EPSG:4326 llega en el orden de ejes oficial latitud, longitud.
    return [[round(values[i + 1], 6), round(values[i], 6)] for i in range(0, len(values), 2)]


def municipality_features(gml_bytes):
    root = ET.fromstring(gml_bytes)
    features = []
    for unit in root.findall("wfs:member/au:AdministrativeUnit", NS):
        name_node = unit.find("au:name/gn:GeographicalName/gn:spelling/gn:SpellingOfName/gn:text", NS)
        code_node = unit.find("au:nationalCode", NS)
        if name_node is None or code_node is None:
            continue
        polygons = []
        for polygon in unit.findall("au:geometry/gml:MultiSurface/gml:surfaceMember/gml:Polygon", NS):
            exterior = polygon.find("gml:exterior/gml:LinearRing/gml:posList", NS)
            if exterior is None:
                continue
            rings = [simplify_ring(parse_pos_list(exterior), 0.00018)]
            for interior in polygon.findall("gml:interior/gml:LinearRing/gml:posList", NS):
                rings.append(simplify_ring(parse_pos_list(interior), 0.00018))
            polygons.append(rings)
        if not polygons:
            continue
        geometry = (
            {"type": "Polygon", "coordinates": polygons[0]}
            if len(polygons) == 1
            else {"type": "MultiPolygon", "coordinates": polygons}
        )
        features.append({
            "type": "Feature",
            "id": f"municipio-{code_node.text[-3:]}",
            "properties": {
                "nombre": name_node.text.strip(),
                "tipo": "municipio",
                "contexto": "Comunidad de Madrid",
            },
            "geometry": geometry,
        })
    return features


def main():
    barrios = topo_features(download_json(BARRIOS_URL), "Barrios", "barrio")
    distritos = topo_features(download_json(DISTRITOS_URL), "Distritos", "distrito")
    municipios = municipality_features(download_municipios())
    if len(barrios) != 131 or len(distritos) != 21 or len(municipios) != 179:
        raise RuntimeError(
            f"Recuento inesperado: {len(barrios)} barrios, {len(distritos)} distritos, "
            f"{len(municipios)} municipios"
        )

    collection = {
        "type": "FeatureCollection",
        "generated": date.today().isoformat(),
        "sources": [
            {"name": "Geoportal del Ayuntamiento de Madrid", "url": BARRIOS_URL},
            {"name": "IGN-CNIG, WFS INSPIRE Unidades Administrativas", "url": IGN_WFS_URL},
        ],
        "features": barrios + distritos + sorted(
            municipios, key=lambda feature: feature["properties"]["nombre"]
        ),
    }
    with open(OUTPUT, "w", encoding="utf-8", newline="\n") as output:
        json.dump(collection, output, ensure_ascii=False, separators=(",", ":"))
        output.write("\n")
    print(
        f"Generado {os.path.basename(OUTPUT)}: {len(barrios)} barrios, "
        f"{len(distritos)} distritos y {len(municipios)} municipios"
    )


if __name__ == "__main__":
    main()
