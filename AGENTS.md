# Dónde estudiar en Madrid

Mapa web que muestra lugares para estudiar en Madrid (bibliotecas, salas de estudio y
bibliotecas universitarias). Al pulsar un marcador se abre un **panel lateral** con su nombre,
dirección, horario y enlace a su web, y la URL cambia a la página propia de ese centro.
Minimalista: solo mapa + marcadores + panel. Sin menús, buscador ni backend.

- **Web:** https://bibliotecasmadrid.github.io/Donde-estudio-hoy/
- **Repo:** https://github.com/bibliotecasmadrid/Donde-estudio-hoy

## Estructura

- **`index.html`** — la app del mapa (HTML + CSS + JS en un archivo). Contiene el array
  `lugares` (fuente única de datos), la lógica de Leaflet y el panel lateral.
- **`build.py`** — script que **lee el array `lugares` de `index.html`** y genera:
  - una página HTML por cada centro (`<slug>.html`, p. ej. `clara-campoamor.html`), optimizada
    para SEO (title, meta, canonical, JSON-LD propio);
  - el `sitemap.xml`.
- **`<slug>.html`** (×137) — páginas de detalle generadas (NO editar a mano; se regeneran).
- **`sitemap.xml`** — generado por `build.py`.
- **`google….html`** — verificación de Google Search Console.
- **`manifest.json` + `sw.js` + `icons/`** — hacen la web una **PWA instalable**. El service
  worker es "siempre online" (no cachea datos: un cambio en la web se ve al instante). Es además
  la base para la **app Android (TWA)** publicable en Google Play, que envuelve esta misma web,
  así que **no hay datos duplicados**: se edita solo aquí.

Stack: [Leaflet](https://leafletjs.com/) 1.9.4 (CDN) sobre teselas CARTO Positron. Hosting en
GitHub Pages (rama `main`, raíz).

### Slugs (URL de cada centro)

Cada centro tiene su URL `…/Donde-estudio-hoy/<slug>` (sin extensión; GitHub Pages sirve
`<slug>.html`). El slug se calcula desde `nombre` quitando prefijos genéricos
("Sala de Estudio", "Biblioteca Pública/Municipal"…) y normalizando. **El algoritmo está
duplicado** en `slugify()` de `index.html` (JS) y `slugify()` de `build.py` (Python) y **deben
ser idénticos** para que el panel enlace a la página correcta. Si tocas uno, toca el otro.

## Datos: array `lugares`

Cada lugar es un objeto:

```javascript
{
  tipo: "biblioteca" | "sala" | "universidad",  // define color y badge
  nombre: "...",
  distrito: "...",
  direccion: "...",
  lat: 40.4274, lng: -3.7106,                   // grados decimales
  horario: "Lun–Vie 9–21h\n(...)",              // \n = nueva línea en el popup
  web: "https://..."                            // OPCIONAL: si falta, el botón enlaza a una
                                                // búsqueda en Google del nombre
}
```

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
