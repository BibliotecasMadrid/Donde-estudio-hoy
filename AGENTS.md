# Dónde estudiar en Madrid

Mapa web que muestra lugares para estudiar en Madrid (bibliotecas, salas de estudio y
bibliotecas universitarias). Al pulsar un marcador aparece su nombre, dirección, horario y un
enlace a su web. Minimalista: solo mapa + marcadores + popups. Sin menús, buscador ni backend.

- **Web:** https://bibliotecasmadrid.github.io/Donde-estudio-hoy/
- **Repo:** https://github.com/bibliotecasmadrid/Donde-estudio-hoy

## Estructura

Todo vive en **`index.html`** (HTML + CSS + JS en un solo archivo, sin build ni dependencias):
1. `<style>` — estilos del mapa, cabecera, leyenda y popups.
2. `<body>` — `#map`, `.topbar`, `.legend`.
3. `<script>` — el array `lugares` (los datos) + la lógica de Leaflet.

Stack: [Leaflet](https://leafletjs.com/) 1.9.4 (CDN) sobre teselas CARTO Positron. Hosting en
GitHub Pages (rama `main`, raíz).

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
python -m http.server 3456     # luego abrir http://localhost:3456
git add index.html && git commit -m "..." && git push origin main   # Pages reconstruye en ~1-2 min
```

## Datos y licencia

Bibliotecas y salas: [datos.madrid.es](https://datos.madrid.es) (CC BY 4.0). Universidades:
webs oficiales de cada institución. Conservar la atribución del mapa (abajo a la derecha).
