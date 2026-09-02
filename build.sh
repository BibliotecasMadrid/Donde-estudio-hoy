#!/usr/bin/env bash
# Construye lo que Cloudflare Pages publica en https://bibliotecasmadrid.es
#
# En el panel (Pages -> el proyecto -> Settings -> Build):
#     Build command:            bash build.sh
#     Build output directory:   dist
#
# Hace dos cosas:
#
#   1. Ejecuta build.py, que regenera las paginas <slug>.html y el sitemap a partir del
#      array `lugares` de index.html. Se hace AQUI, en cada despliegue, para que la web
#      publicada no pueda quedarse desincronizada de index.html por un olvido. index.html
#      es la unica fuente de datos; todo lo demas se deriva.
#
#   2. Copia a dist/ solo lo que es web. Por defecto Pages publicaria el repo entero, y
#      aqui eso importa: "BiblioMadrid - Google Play package" contiene el material de
#      firma de la app Android. Al final hay una comprobacion que aborta el despliegue si
#      ese material aparece en dist/ por cualquier via.
#
# Si algo de esto falla, el despliegue falla y queda publicada la ultima version buena.
# Es lo que se busca: mejor no publicar que publicar a medias.

set -euo pipefail

SALIDA="dist"

# --- 1. Regenerar las paginas de cada centro y el sitemap ---

# No basta con que el comando exista: en Windows "python3" es un stub de la Microsoft
# Store que esta en el PATH pero no ejecuta nada. Hay que probarlo de verdad.
PY=""
for candidato in python3 python; do
  if command -v "$candidato" >/dev/null 2>&1 && "$candidato" -c "" >/dev/null 2>&1; then
    PY="$candidato"
    break
  fi
done

if [[ -z "$PY" ]]; then
  echo "ERROR: no hay Python utilizable. build.py no puede generar las paginas." >&2
  exit 1
fi

# El generador imprime nombres con acentos; sin esto, un entorno con locale raro peta.
export PYTHONIOENCODING=utf-8

echo "==> Generando paginas con $PY build.py"
"$PY" build.py
ANIO_CALENDARIO="$("$PY" -c 'import json; print(json.load(open("calendario.json", encoding="utf-8"))["year"])')"
ANIO_ACTUAL="$(date +%Y)"
[[ "$ANIO_CALENDARIO" =~ ^[0-9]{4}$ ]] || { echo "ERROR: año de calendario inválido" >&2; exit 1; }

# En enero, no se permite publicar el calendario vencido del año anterior.
if (( 10#$ANIO_CALENDARIO < 10#$ANIO_ACTUAL )); then
  echo "ERROR: calendario $ANIO_CALENDARIO vencido; carga el calendario de $ANIO_ACTUAL antes de desplegar." >&2
  exit 1
fi

# --- 2. Armar dist/ ---

# Lo que NO es web. Todo lo que no este aqui se publica.
PRIVADO=(
  "BiblioMadrid - Google Play package"   # material de firma de la app Android
  "build.py"                             # el generador, no su salida
  "build.sh"                             # este mismo script
  "sync_uam.py"
  "test_build.py"
  "fotos.py"                             # herramienta de fotos, no su salida
  "generar_zonas.py"                     # genera la cartografia local del buscador
  ".fotos-cache"                         # originales descargados de Google Places
  ".env"                                 # claves de API: NUNCA en dist/
  "*.env"
  "calendario.json"                      # fuente privada; build.py publica /horarios/
  "AGENTS.md"
  "README.md"
  "AUDITORIA_*.md"                       # documentación de trabajo, no contenido web
  "__pycache__"
  ".git"
  ".gitignore"
  ".github"
  ".claude"
  ".python-version"
)

es_privado() {
  local nombre="$1" p
  for p in "${PRIVADO[@]}"; do
    # $p sin comillas: permite patrones como "*.env" ademas de nombres exactos.
    [[ "$nombre" == $p ]] && return 0
  done
  return 1
}

rm -rf "$SALIDA"
mkdir -p "$SALIDA"

# dotglob para que entre .well-known/ (la validacion de la app Android vive ahi).
shopt -s dotglob nullglob
for ruta in ./*; do
  nombre="$(basename "$ruta")"
  [[ "$nombre" == "$SALIDA" ]] && continue
  es_privado "$nombre" && continue
  cp -R "$ruta" "$SALIDA"/
done
shopt -u dotglob nullglob

# --- 3. Comprobaciones. Si alguna falla, no se publica nada ---

fallo() { echo "ERROR: $1" >&2; exit 1; }

[[ -f "$SALIDA/index.html" ]] || fallo "falta index.html"
[[ -f "$SALIDA/sitemap.xml" ]] || fallo "falta sitemap.xml"
[[ -f "$SALIDA/horarios.js" ]] || fallo "falta horarios.js"
[[ -f "$SALIDA/basemap.js" ]] || fallo "falta basemap.js (los mapas se quedarian sin capa base)"
[[ -f "$SALIDA/zonas-madrid.geojson" ]] || fallo "falta zonas-madrid.geojson (el buscador no encontraria barrios ni municipios)"
[[ -f "$SALIDA/manifest.json" ]] || fallo "falta manifest.json (la PWA dejaria de instalarse)"
[[ -f "$SALIDA/sw.js" ]] || fallo "falta sw.js (la PWA dejaria de instalarse)"
[[ -f "$SALIDA/.well-known/assetlinks.json" ]] || fallo "falta .well-known/assetlinks.json (la app Android dejaria de validar el dominio)"

# El estado abierto/cerrado depende de estos 12 assets generados, no del texto
# editorial de index.html. No publicar si el calendario anual quedó incompleto.
for mes in {01..12}; do
  [[ -f "$SALIDA/horarios/$ANIO_CALENDARIO-$mes.json" ]] || fallo "falta horarios/$ANIO_CALENDARIO-$mes.json"
done

# Red de seguridad: da igual como se llame la carpeta, el material de firma no sale de
# aqui. Los .zip entran en la lista porque el paquete que descarga PWABuilder ES un zip
# con el keystore y sus contrasenas dentro, y el 25/08/2026 uno acabo en la raiz del
# repo: por nombre no lo habria cazado ninguna de las reglas de abajo.
if find "$SALIDA" \( -iname "*.keystore" -o -iname "*.jks" -o -iname "*.aab" \
                  -o -iname "*.apk" -o -iname "*.zip" -o -iname "*key-info*" \) -print -quit | grep -q .; then
  fallo "material de firma de la app dentro de $SALIDA. Abortado."
fi

# Misma logica para las claves de API: la de Google Places se usa desde fotos.py y vive
# fuera del repo, pero si alguna vez aparece un .env aqui no se publica nada.
if find "$SALIDA" \( -name "*.env" -o -name ".env" \) -print -quit | grep -q .; then
  fallo "un archivo .env dentro de $SALIDA. Abortado."
fi

# Si el generador fallara a medias, mejor enterarse aqui que en Google.
PAGINAS=$(find "$SALIDA" -maxdepth 1 -name "*.html" | wc -l)
[[ "$PAGINAS" -ge 200 ]] || fallo "solo $PAGINAS paginas HTML; se esperaban 200 o mas. build.py fallo a medias?"

echo "==> Listo: $PAGINAS paginas y $(find "$SALIDA" -type f | wc -l) archivos en $SALIDA/"
