# Dónde estudiar en Madrid

Mapa web que muestra lugares para estudiar en Madrid (bibliotecas, salas de estudio y
bibliotecas universitarias). Al pulsar un marcador se abre un **panel lateral** con su nombre,
dirección, horario y enlace a su web, y la URL cambia a la página propia de ese centro.
Minimalista: solo mapa + marcadores + panel. Sin menús, buscador ni backend.

- **Web:** https://bibliotecasmadrid.es/
- **Repo:** https://github.com/bibliotecasmadrid/Donde-estudio-hoy

## Estructura

- **`index.html`** — la app del mapa (HTML + CSS + JS en un archivo). Contiene el array
  `lugares` (fuente única de datos), la lógica de Leaflet y el panel lateral.
- **`build.py`** — script que **lee el array `lugares` de `index.html`** y genera:
  - una página HTML por cada centro (`<slug>.html`, p. ej. `clara-campoamor.html`), optimizada
    para SEO (title, meta, canonical, JSON-LD propio);
  - el `sitemap.xml`.
- **`<slug>.html`** (×217) — páginas de detalle generadas (NO editar a mano). `build.sh` las
  regenera **en cada despliegue**, así que lo que se publica siempre sale de `index.html`.
- **`calendario.json`** — calendario interno 2026 con festivos, periodos estivales y excepciones.
- **`sitemap.xml`** — generado por `build.py`.
- **`build.sh`** — lo que ejecuta Cloudflare Pages: lanza `build.py` y arma `dist/` con solo
  lo que es web. Aborta el despliegue si el material de firma de la app se cuela en `dist/`.
- **`_headers`** — cabeceras HTTP (seguridad y caché) que aplica Cloudflare Pages.
- **`robots.txt`, `404.html`** — página de error propia, con vuelta al mapa.
- **`.well-known/assetlinks.json`** — lo que Google lee para validar que la app Android
  es dueña del dominio. Si falta, la app deja de abrirse a pantalla completa.
- **`google….html`** — verificación de Google Search Console.
- **`manifest.json` + `sw.js` + `icons/`** — hacen la web una **PWA instalable**. El service
  worker es "siempre online" (no cachea datos: un cambio en la web se ve al instante). Es además
  la base para la **app Android (TWA)** publicable en Google Play, que envuelve esta misma web,
  así que **no hay datos duplicados**: se edita solo aquí.

Stack: [Leaflet](https://leafletjs.com/) 1.9.4 (CDN) sobre teselas CARTO Positron. Hosting en
**Cloudflare Pages**: cada push a `main` despliega. `build.sh` arma la carpeta `dist` con lo
que es web y deja fuera el keystore de firma, los scripts y los temporales.

### Slugs (URL de cada centro)

Cada centro tiene su URL `https://bibliotecasmadrid.es/<slug>` (sin extensión; Cloudflare
Pages sirve `<slug>.html`). El slug se calcula desde `nombre` quitando prefijos genéricos
("Sala de Estudio", "Biblioteca Pública/Municipal"…) y normalizando. **El algoritmo está
duplicado** en `slugify()` de `index.html` (JS) y `slugify()` de `build.py` (Python) y **deben
ser idénticos** para que el panel enlace a la página correcta. Si tocas uno, toca el otro.

**Cambiar `nombre` cambia la URL.** El slug se deriva del nombre, así que corregir el nombre
de un centro renombra su página y deja un 404 donde antes había una URL indexada y enlazada.
Cuando haya que hacerlo, añadir un 301 en `_redirects` de la URL vieja a la nueva. Ojo además
con `unique_slugs()`: desempata colisiones con sufijos `-2`, `-3` **según el orden del array**,
así que renombrar un centro puede mover el sufijo de OTRO distinto. La forma segura de saber
qué URLs cambian es recalcular `unique_slugs()` sobre la lista ya renombrada y comparar.

## Datos: array `lugares`

Cada lugar es un objeto:

```javascript
{
  tipo: "biblioteca" | "sala" | "universidad",  // define color y badge
  nombre: "...",
  distrito: "...",
  direccion: "...",
  lat: 40.4274, lng: -3.7106,                   // grados decimales
  plazas: 250,                                  // aforo / puestos de estudio disponibles
  horario: "Lun–Vie 9–21h\n(...)",              // \n = nueva línea en el popup
  web: "https://...",                           // OPCIONAL: si falta, el botón enlaza a una
                                                // búsqueda en Google del nombre

  // ── Fotos: son DOS, y cada una sale en un sitio distinto ──
  foto: "images/x-exterior.jpg",                // EXTERIOR del edificio. Fondo a pantalla
                                                // completa de la ficha <slug>.html.
  foto_interior: "images/x-interior.jpg",       // INTERIOR: la sala de estudio, mesas y
                                                // sillas. Cover del panel del mapa.
  foto_credito: "Nombre del autor",             // OPCIONALES, pero OBLIGATORIOS si la foto
  foto_interior_credito: "Nombre del autor"     // viene de Google Places: sus términos
                                                // exigen acreditar al autor.
}
```

Las dos fotos son opcionales y degradan con cabeza: sin `foto_interior`, el panel del mapa cae en
`foto`; sin ninguna de las dos, en el pool genérico de `PHOTO_POOLS`. Así se pueden ir rellenando
por lotes sin romper nada. Se traen con `fotos.py` (Google Places API) y se guardan ya
redimensionadas en `images/`: 800×500 los interiores (el cover del panel mide 160 px de alto) y
1600 px de ancho los exteriores (van a pantalla completa).

**Ojo:** `extract_lugares()` de `build.py` parsea el array con una **lista blanca de campos**. Un
campo que no esté en ese `re.sub` no llega a JSON válido y **el build entero falla**. Si añades un
campo al array, añádelo también ahí.

Colores por tipo: `biblioteca` azul `#2563EB`, `sala` verde `#059669`, `universidad` morado
`#7C3AED`. **Ojo:** el color se define en el objeto `colores` (JS) y también en `:root` + la
leyenda (CSS/HTML); si cambias uno, cambia los demás.

Para añadir un lugar, copia un objeto del array y rellénalo. Coordenadas con Nominatim:
`curl -A "DondeEstudioHoy/1.0" "https://nominatim.openstreetmap.org/search?street=Calle+X+1&city=Madrid&format=json&limit=1"`
(límite 1 req/seg; la búsqueda por calle es más fiable que el texto libre).

## Local y despliegue

```bash
python build.py                # REGENERA las páginas por centro + sitemap (tras tocar los datos)
python -m http.server 3456     # luego abrir http://localhost:3456
git add -A && git commit -m "..." && git push origin main   # Pages reconstruye en ~1-2 min
```

**Importante:** después de añadir/editar lugares en `index.html`, ejecuta `python build.py`
para regenerar las páginas y el sitemap antes de commitear.

## App Android (PWA → TWA en Google Play)

La app de la tienda es una **Trusted Web Activity**: una cáscara que abre esta web a pantalla
completa. No tiene datos propios; siempre carga la web en vivo. Pasos para publicarla:

1. La web ya es PWA válida (`manifest.json` + `sw.js` + iconos, sobre HTTPS).
2. En [PWABuilder](https://www.pwabuilder.com) introducir la URL del sitio, generar el paquete
   **Android (AAB)** y descargarlo. Anotar la **huella SHA-256** del certificado de firma que
   indica PWABuilder.
3. Crear `/.well-known/assetlinks.json` en el repo con esa huella (Digital Asset Links) para
   verificar el dominio y quitar la barra de URL en la app.
4. Subir el AAB a **Google Play Console** (cuenta de pago único 25 $) y publicar.

Para actualizar la app basta con actualizar la web: el contenido es el mismo. Solo hay que
volver a publicar el AAB si cambian icono, nombre o configuración de la propia cáscara.

## Datos y licencia

Bibliotecas y salas: [datos.madrid.es](https://datos.madrid.es) (CC BY 4.0). Universidades:
webs oficiales de cada institución. Conservar la atribución del mapa (abajo a la derecha).
