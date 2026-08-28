// basemap.js - La capa base de los mapas, en un solo sitio.
//
// Por que existe este archivo: en agosto de 2026 CARTO cerro las teselas gratuitas de
// basemaps.cartocdn.com. No devuelven un error, que se veria enseguida; devuelven la
// imagen de siempre con "API KEY REQUIRED" escrito encima. Los endpoints antiguos
// (cartodb-basemaps-*.global.ssl.fastly.net, /rastertiles/voyager) hacen lo mismo.
//
// Hay dos salidas y aqui estan las dos:
//
//   1. Sin clave, que es lo que esta activo. El estilo Positron de OpenFreeMap: el mismo
//      diseno claro de siempre, sin clave, sin cuota y con uso en apps permitido (lo que
//      importa aqui, porque la web tambien se publica como app Android). Es vectorial, asi
//      que necesita MapLibre GL; se carga solo en este caso y solo en paginas con mapa.
//
//   2. Con clave de CARTO. Rellena CARTO_API_KEY abajo y el mapa vuelve a las teselas
//      raster de antes, sin cargar MapLibre. La clave viaja en el HTML publico: es lo
//      normal en las claves de basemap, pero limitala por dominio en el panel de CARTO.
//
// Cambiar de una a otra es cambiar esa constante. Nada mas depende de la eleccion.

window.Basemap = (function () {
  'use strict';

  const CARTO_API_KEY = '';   // vacio = OpenFreeMap; con clave = CARTO Positron raster

  const MAPLIBRE_VER = '5.24.0';
  const MAPLIBRE_JS = 'https://unpkg.com/maplibre-gl@' + MAPLIBRE_VER + '/dist/maplibre-gl.js';
  const MAPLIBRE_CSS = 'https://unpkg.com/maplibre-gl@' + MAPLIBRE_VER + '/dist/maplibre-gl.css';
  const MAPLIBRE_LEAFLET_JS = 'https://unpkg.com/@maplibre/maplibre-gl-leaflet@0.1.4/leaflet-maplibre-gl.js';
  const ESTILO_POSITRON = 'https://tiles.openfreemap.org/styles/positron';

  const OSM = '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>';

  function cargarCss(href) {
    if (document.querySelector('link[href="' + href + '"]')) return;
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = href;
    document.head.appendChild(link);
  }

  function cargarScript(src) {
    return new Promise(function (resolve, reject) {
      const previo = document.querySelector('script[src="' + src + '"]');
      if (previo) {
        previo.addEventListener('load', resolve);
        previo.addEventListener('error', reject);
        return;
      }
      const script = document.createElement('script');
      script.src = src;
      script.async = true;
      script.onload = resolve;
      script.onerror = function () { reject(new Error('No se pudo cargar ' + src)); };
      document.head.appendChild(script);
    });
  }

  function atribucion(map, texto) {
    map.attributionControl.addAttribution(texto);
  }

  function carto(map, extra) {
    L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png?api_key=' + CARTO_API_KEY, {
      attribution: OSM + ' · © <a href="https://carto.com/attributions">CARTO</a>' + extra,
      subdomains: 'abcd',
      maxZoom: 20
    }).addTo(map);
  }

  // Red de seguridad para cuando unpkg u OpenFreeMap no respondan. Sin esto el mapa se
  // queda en blanco con los marcadores flotando. Es un plan B puntual, no la capa normal:
  // la politica de teselas de openstreetmap.org no admite que una app tire de ellas.
  function osmRaster(map, extra) {
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: OSM + extra,
      maxNativeZoom: 19,
      maxZoom: 20
    }).addTo(map);
  }

  async function openfreemap(map, extra) {
    cargarCss(MAPLIBRE_CSS);
    await cargarScript(MAPLIBRE_JS);
    await cargarScript(MAPLIBRE_LEAFLET_JS);
    L.maplibreGL({ style: ESTILO_POSITRON, attribution: '' }).addTo(map);
    atribucion(map, OSM + ' · <a href="https://openfreemap.org">OpenFreeMap</a>' + extra);
  }

  /**
   * Anade la capa base a un mapa de Leaflet ya creado.
   * @param {L.Map} map
   * @param {string} [extra] Atribucion adicional, ya en HTML (ej. la fuente de los datos).
   */
  function add(map, extra) {
    const sufijo = extra ? ' · ' + extra : '';

    // Esto tiene que pasar YA, no dentro del await de abajo. Antes el zoom maximo lo traia
    // la capa raster, que se anadia de forma sincrona; markerCluster lo lee al crearse
    // (justo despues de esta llamada) para construir su rejilla, y MapLibre se niega a
    // arrancar sobre un mapa sin maxZoom. Si se fija mas tarde, markerCluster ya ha leido
    // Infinity y el mapa se queda sin un solo marcador, con las fichas listadas igual.
    if (map.options.maxZoom == null) map.setMaxZoom(20);

    if (CARTO_API_KEY) {
      carto(map, sufijo);
      return Promise.resolve();
    }
    return openfreemap(map, sufijo).catch(function (error) {
      console.warn('Capa base vectorial no disponible, se usa la de respaldo:', error);
      osmRaster(map, sufijo);
    });
  }

  return { add: add };
})();
