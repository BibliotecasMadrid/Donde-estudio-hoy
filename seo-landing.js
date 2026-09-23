(function () {
  'use strict';

  const data = window.LANDING_DATA;
  if (!data || !window.L || !window.Horarios || !window.Basemap) return;

  const results = document.getElementById('results');
  const summary = document.getElementById('summary');
  const notice = document.getElementById('notice');
  const panel = document.getElementById('place-panel');
  const panelContent = document.getElementById('panel-content');
  const panelClose = document.getElementById('panel-close');
  const filters = document.getElementById('filters');
  const mapColumn = document.querySelector('.map-column');
  let activeFilter = 'all';
  let visiblePlaces = [...data.places];
  let selectedSlug = null;
  let userLocation = null;

  const escapeHtml = value => String(value == null ? '' : value)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#039;');

  const MONTHS = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];
  const WEEKDAYS = ['domingo', 'lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado'];
  const keyParts = key => key.split('-').map(Number);
  const keyWeekday = key => { const [y, m, d] = keyParts(key); return new Date(Date.UTC(y, m - 1, d, 12)).getUTCDay(); };

  // Siempre en hora de Madrid, que es la que manda el calendario: a las 00:30 del
  // sábado en Madrid ya es sábado aunque el visitante tenga el reloj en otra zona.
  function renderDates() {
    const today = Horarios.dateKey(new Date());
    const [year, month, day] = keyParts(today);
    const updated = document.getElementById('updated');
    if (updated) updated.textContent = `Actualizado: ${WEEKDAYS[keyWeekday(today)]}, ${day} de ${MONTHS[month - 1]} de ${year}`;

    const target = document.getElementById('weekend-dates');
    if (!target) return;
    const keys = Horarios.weekendKeys(new Date());
    const [, satMonth, satDay] = keyParts(keys.saturday);
    const [, sunMonth, sunDay] = keyParts(keys.sunday);
    const saturday = `sábado ${satDay}${satMonth === sunMonth ? '' : ` de ${MONTHS[satMonth - 1]}`}`;
    const sunday = `domingo ${sunDay} de ${MONTHS[sunMonth - 1]}`;
    if (today === keys.saturday) target.textContent = `hoy, ${saturday}, y mañana, ${sunday}`;
    else if (today === keys.sunday) target.textContent = `ayer, ${saturday}, y hoy, ${sunday}`;
    else target.textContent = `este ${saturday} y ${sunday}`;
  }
  renderDates();
  // Si la pestaña queda abierta de un día para otro, las fechas no se quedan atrás.
  document.addEventListener('visibilitychange', () => { if (!document.hidden) renderDates(); });

  const map = L.map('map', { center: [40.4168, -3.7038], zoom: 11 });
  window.Basemap.add(map);
  const mobileMapMedia = window.matchMedia('(max-width: 768px)');
  const mapAttribution = map.attributionControl.getContainer();

  function setAttributionExpanded(expanded) {
    mapAttribution.classList.toggle('is-expanded', expanded);
    mapAttribution.setAttribute('aria-expanded', String(expanded));
    mapAttribution.setAttribute('aria-label', expanded ? 'Ocultar créditos del mapa' : 'Mostrar créditos del mapa');
  }

  function syncAttribution() {
    if (mobileMapMedia.matches) {
      mapAttribution.tabIndex = 0;
      mapAttribution.setAttribute('role', 'button');
      mapAttribution.title = 'Créditos del mapa';
      if (!mapAttribution.hasAttribute('aria-expanded')) setAttributionExpanded(false);
    } else {
      mapAttribution.classList.remove('is-expanded');
      mapAttribution.removeAttribute('tabindex');
      mapAttribution.removeAttribute('role');
      mapAttribution.removeAttribute('title');
      mapAttribution.removeAttribute('aria-label');
      mapAttribution.removeAttribute('aria-expanded');
    }
  }

  mapAttribution.addEventListener('click', event => {
    if (!mobileMapMedia.matches) return;
    event.preventDefault();
    event.stopPropagation();
    setAttributionExpanded(!mapAttribution.classList.contains('is-expanded'));
  });
  mapAttribution.addEventListener('keydown', event => {
    if (!mobileMapMedia.matches || (event.key !== 'Enter' && event.key !== ' ')) return;
    event.preventDefault();
    setAttributionExpanded(!mapAttribution.classList.contains('is-expanded'));
  });
  if (typeof mobileMapMedia.addEventListener === 'function') mobileMapMedia.addEventListener('change', syncAttribution);
  else mobileMapMedia.addListener(syncAttribution);
  syncAttribution();
  let userMarker = null;
  const LocateControl = L.Control.extend({
    options: { position: 'topleft' },
    onAdd() {
      const button = L.DomUtil.create('button', 'locate-button leaflet-control');
      button.type = 'button';
      button.title = 'Mi ubicación';
      button.setAttribute('aria-label', 'Ordenar por cercanía a mi ubicación');
      button.innerHTML = '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polygon points="3 11 22 2 13 21 11 13 3 11"/></svg>';
      L.DomEvent.disableClickPropagation(button);
      L.DomEvent.on(button, 'click', requestLocation);
      return button;
    }
  });
  const locateButton = new LocateControl().addTo(map).getContainer();

  function setLocating(loading) {
    locateButton.classList.toggle('is-locating', loading);
    locateButton.setAttribute('aria-busy', String(loading));
  }

  function showLocationError() {
    notice.hidden = false;
    notice.dataset.kind = 'location';
    notice.textContent = 'No se ha podido obtener tu ubicación. Revisa los permisos de ubicación del navegador.';
  }

  function useLocation(position, center) {
    userLocation = L.latLng(position.coords.latitude, position.coords.longitude);
    if (userMarker) userMarker.setLatLng(userLocation);
    else {
      const icon = L.divIcon({ className: 'user-marker', iconSize: [18, 18], iconAnchor: [9, 9], html: '<span></span>' });
      userMarker = L.marker(userLocation, { icon, title: 'Tu ubicación', zIndexOffset: 900, keyboard: false })
        .bindTooltip('Estás aquí', { direction: 'top', offset: [0, -8] }).addTo(map);
    }
    locateButton.classList.add('is-active');
    for (const place of data.places) place.distance = userLocation.distanceTo([place.lat, place.lng]);
    rerender(false);
    if (center) {
      const nearest = [...visiblePlaces].sort((a, b) => a.distance - b.distance).slice(0, 3);
      map.fitBounds(L.latLngBounds([userLocation, ...nearest.map(place => [place.lat, place.lng])]).pad(.25), { maxZoom: 15 });
      results.closest('.results-column').scrollTop = 0;
    }
  }

  function requestLocation() {
    if (!navigator.geolocation) { showLocationError(); return; }
    setLocating(true);
    navigator.geolocation.getCurrentPosition(position => {
      setLocating(false);
      if (notice.dataset.kind === 'location') notice.hidden = true;
      useLocation(position, true);
    }, () => {
      setLocating(false);
      showLocationError();
    }, { enableHighAccuracy: false, maximumAge: 5 * 60 * 1000, timeout: 8000 });
  }

  function formatDistance(meters) {
    if (meters == null) return '';
    if (meters < 1000) return `${Math.max(50, Math.round(meters / 50) * 50)} m`;
    return `${(meters / 1000).toLocaleString('es-ES', { maximumFractionDigits: meters < 10000 ? 1 : 0 })} km`;
  }

  const clusters = L.markerClusterGroup({ showCoverageOnHover: false, maxClusterRadius: 45 }).addTo(map);
  const markers = new Map();

  function markerIcon(place) {
    return L.divIcon({
      className: '', iconSize: [26, 34], iconAnchor: [13, 32],
      html: `<svg width="26" height="34" viewBox="0 0 26 34" aria-hidden="true"><path d="M13 33S1 21.2 1 12.8A12 12 0 0 1 25 12.8C25 21.2 13 33 13 33Z" fill="${place.color}" stroke="white" stroke-width="2"/><circle cx="13" cy="13" r="4" fill="white"/></svg>`
    });
  }

  for (const place of data.places) {
    const marker = L.marker([place.lat, place.lng], { icon: markerIcon(place), title: place.name });
    marker.bindTooltip(place.name, { direction: 'top', offset: [0, -28] });
    marker.on('click', () => openPanel(place, true, true));
    markers.set(place.slug, marker);
  }

  function formatEntry(entry) {
    if (!entry || entry.estado === 'consultar') return 'Consultar';
    if (entry.estado !== 'abierto') return 'Cerrado';
    return Horarios.formatIntervals(entry.intervalos) || 'Consultar';
  }

  function periodLabel(period) {
    return `${Horarios.dayLabel(period.from)} – ${Horarios.dayLabel(period.to)}`;
  }

  function placeCard(place) {
    const runtime = place.runtime || {};
    let status = '';
    let schedule = '';
    if (data.mode === 'weekend') {
      schedule = `<div class="schedule-row"><span>${escapeHtml(runtime.saturdayLabel || 'Sábado habitual')}</span><strong>${escapeHtml(formatEntry(runtime.saturday || place.weekend.saturday))}</strong></div>
        <div class="schedule-row"><span>${escapeHtml(runtime.sundayLabel || 'Domingo habitual')}</span><strong>${escapeHtml(formatEntry(runtime.sunday || place.weekend.sunday))}</strong></div>`;
    } else {
      const statusClass = runtime.failed ? 'unknown' : runtime.active ? 'active' : 'inactive';
      const statusText = runtime.failed ? 'Sin comprobar' : runtime.active ? '24 h hoy' : 'No activo hoy';
      status = `<span class="status-pill ${statusClass}">${statusText}</span>`;
      schedule = place.periods.map(period => `<div class="period"><strong>${escapeHtml(periodLabel(period))}</strong><a href="${escapeHtml(period.source.url)}" rel="noopener noreferrer">Fuente oficial</a></div>`).join('');
    }
    const distance = userLocation && place.distance != null ? `<span class="distance">${formatDistance(place.distance)}</span>` : '';
    return `<article class="place-card${place.slug === selectedSlug ? ' selected' : ''}" data-slug="${place.slug}" tabindex="0">
      <div class="card-top"><span class="type-badge" style="--type-color:${place.color}">${escapeHtml(place.typeLabel)}</span><span class="card-top-end">${distance}${status}</span></div>
      <h3>${escapeHtml(place.name)}</h3><p>${escapeHtml(place.district)} · ${escapeHtml(place.address)}</p>
      <div class="card-schedule">${schedule}</div><a class="detail-link" href="/${place.slug}">Ver ficha y próximos horarios</a>
    </article>`;
  }

  function sortPlaces(places) {
    if (userLocation) return [...places].sort((a, b) => {
      if (data.mode === 'full-day' && Boolean((a.runtime || {}).active) !== Boolean((b.runtime || {}).active)) return (a.runtime || {}).active ? -1 : 1;
      return a.distance - b.distance;
    });
    return [...places].sort((a, b) => {
      const ar = a.runtime || {}, br = b.runtime || {};
      if (data.mode === 'full-day' && Boolean(ar.active) !== Boolean(br.active)) return ar.active ? -1 : 1;
      const aBoth = Boolean(ar.satOpen && ar.sunOpen), bBoth = Boolean(br.satOpen && br.sunOpen);
      if (aBoth !== bBoth) return aBoth ? -1 : 1;
      if (Boolean(ar.sunOpen) !== Boolean(br.sunOpen)) return ar.sunOpen ? -1 : 1;
      return a.name.localeCompare(b.name, 'es', { sensitivity: 'base' });
    });
  }

  function renderGroups(places) {
    if (!places.length) {
      results.innerHTML = `<div class="empty-state">No hay centros que coincidan con este filtro. Prueba con otro día o consulta las fichas individuales.</div>`;
      return;
    }
    if (userLocation) {
      results.innerHTML = `<section class="result-group"><h2>Más cerca de ti <span>${places.length}</span></h2><div class="cards">${sortPlaces(places).map(placeCard).join('')}</div></section>`;
      return;
    }
    const groups = [
      ['Madrid capital', places.filter(place => place.municipality === 'madrid')],
      ['Otros municipios', places.filter(place => place.municipality !== 'madrid')]
    ];
    results.innerHTML = groups.filter(([, items]) => items.length).map(([label, items]) =>
      `<section class="result-group"><h2>${label} <span>${items.length}</span></h2><div class="cards">${sortPlaces(items).map(placeCard).join('')}</div></section>`
    ).join('');
  }

  function renderMarkers(places, fit) {
    clusters.clearLayers();
    const selected = places.map(place => markers.get(place.slug)).filter(Boolean);
    if (selected.length) {
      clusters.addLayers(selected);
      if (fit) map.fitBounds(L.latLngBounds(selected.map(marker => marker.getLatLng())).pad(.12), { maxZoom: 13 });
    } else {
      map.setView([40.4168, -3.7038], 10);
    }
  }

  function applyWeekendFilter(fit) {
    visiblePlaces = data.places.filter(place => {
      const state = place.runtime || {};
      if (activeFilter === 'saturday') return state.satOpen;
      if (activeFilter === 'sunday') return state.sunOpen;
      if (activeFilter === 'both') return state.satOpen && state.sunOpen;
      return state.satOpen || state.sunOpen;
    });
    const saturdayCount = data.places.filter(place => place.runtime && place.runtime.satOpen).length;
    const sundayCount = data.places.filter(place => place.runtime && place.runtime.sunOpen).length;
    const bothCount = data.places.filter(place => place.runtime && place.runtime.satOpen && place.runtime.sunOpen).length;
    const selectedLabel = activeFilter === 'both' ? ` · ${bothCount} abiertos ambos días` : activeFilter === 'saturday' ? ` · ${saturdayCount} abiertos el sábado` : activeFilter === 'sunday' ? ` · ${sundayCount} abiertos el domingo` : '';
    summary.textContent = `${visiblePlaces.length} centros mostrados · Sábado ${saturdayCount} · Domingo ${sundayCount}${selectedLabel}`;
    renderGroups(visiblePlaces);
    renderMarkers(visiblePlaces, fit);
  }

  function rerender(fit) {
    // Hasta que carga el calendario no hay nada que reordenar: ya lo hará la carga.
    if (!data.places.every(place => place.runtime)) return;
    if (data.mode === 'weekend') { applyWeekendFilter(fit); return; }
    renderGroups(visiblePlaces);
    renderMarkers(visiblePlaces, fit);
  }

  async function loadWeekend() {
    const keys = Horarios.weekendKeys(new Date());
    const saturdayLabel = Horarios.dayLabel(keys.saturday);
    const sundayLabel = Horarios.dayLabel(keys.sunday);
    try {
      const ids = [...new Set([keys.saturday.slice(0, 7), keys.sunday.slice(0, 7)])];
      await Promise.all(ids.map(id => {
        const [year, month] = id.split('-').map(Number);
        return Horarios.ensureMonth(year, month);
      }));
      for (const place of data.places) {
        const saturday = Horarios.getEntry(place.slug, keys.saturday);
        const sunday = Horarios.getEntry(place.slug, keys.sunday);
        place.runtime = {
          saturday, sunday, saturdayLabel, sundayLabel,
          satOpen: Boolean(saturday && saturday.estado === 'abierto' && saturday.intervalos && saturday.intervalos.length),
          sunOpen: Boolean(sunday && sunday.estado === 'abierto' && sunday.intervalos && sunday.intervalos.length)
        };
      }
    } catch (error) {
      notice.hidden = false;
      notice.dataset.kind = 'calendar';
      notice.textContent = 'No se pudo cargar el calendario de esas fechas. Mostramos el horario habitual; comprueba la ficha y la web oficial antes de desplazarte.';
      for (const place of data.places) {
        place.runtime = {
          saturday: place.weekend.saturday, sunday: place.weekend.sunday,
          saturdayLabel: 'Sábado habitual', sundayLabel: 'Domingo habitual',
          satOpen: place.weekend.saturday.estado === 'abierto' && Boolean(place.weekend.saturday.intervalos.length),
          sunOpen: place.weekend.sunday.estado === 'abierto' && Boolean(place.weekend.sunday.intervalos.length), failed: true
        };
      }
    }
    applyWeekendFilter(true);
  }

  async function loadFullDay() {
    if (!data.places.length) {
      summary.textContent = `No hay aperturas 24 h verificadas en el calendario ${data.calendarYear}.`;
      renderMarkers([], false);
      return;
    }
    try {
      const parts = Horarios.madridParts(new Date());
      if (parts.year !== data.calendarYear) throw new Error('Calendario fuera del año vigente');
      await Horarios.ensureMonth(parts.year, parts.month);
      const today = Horarios.dateKey(new Date());
      for (const place of data.places) {
        const current = Horarios.getEntry(place.slug, today);
        place.runtime = { current, active: Boolean(current && current.estado === 'abierto' && Horarios.formatIntervals(current.intervalos) === '24 h') };
      }
      const active = data.places.filter(place => place.runtime.active).length;
      summary.textContent = active
        ? `${active} ${active === 1 ? 'centro permanece' : 'centros permanecen'} abierto 24 h hoy.`
        : `Hoy no consta ninguna biblioteca abierta 24 h. Hay ${data.places.length} centros con periodos confirmados en ${data.calendarYear}.`;
    } catch (error) {
      for (const place of data.places) place.runtime = { failed: true, active: false };
      notice.hidden = false;
      notice.dataset.kind = 'calendar';
      notice.textContent = 'No se ha podido comprobar el estado de hoy. Consulta cada fuente oficial antes de desplazarte.';
      summary.textContent = `${data.places.length} centros tienen periodos 24 h confirmados en el calendario ${data.calendarYear}. Estado de hoy sin comprobar.`;
    }
    visiblePlaces = [...data.places];
    renderGroups(visiblePlaces);
    renderMarkers(visiblePlaces, true);
  }

  function panelSchedule(place) {
    if (data.mode === 'weekend') {
      const state = place.runtime || {};
      return `<div class="card-schedule"><div class="schedule-row"><span>${escapeHtml(state.saturdayLabel || 'Sábado habitual')}</span><strong>${escapeHtml(formatEntry(state.saturday || place.weekend.saturday))}</strong></div><div class="schedule-row"><span>${escapeHtml(state.sundayLabel || 'Domingo habitual')}</span><strong>${escapeHtml(formatEntry(state.sunday || place.weekend.sunday))}</strong></div></div>`;
    }
    return `<div class="card-schedule">${place.periods.map(period => `<div class="period"><strong>${escapeHtml(periodLabel(period))}</strong><a href="${escapeHtml(period.source.url)}" rel="noopener noreferrer">Fuente</a></div>`).join('')}</div>`;
  }

  function directionsUrl(place) {
    return `https://www.google.com/maps/dir/?api=1&destination=${place.lat},${place.lng}`;
  }

  function markSelectedMarker(slug) {
    markers.forEach((marker, key) => {
      const element = marker.getElement();
      if (element) element.classList.toggle('is-selected', key === slug);
    });
  }

  // La ficha se abre debajo del mapa, dentro de su columna, y el mapa se encoge para
  // hacerle sitio: no flota encima de nada, así que no tapa ni el listado ni la cabecera.
  function openPanel(place, push, fromMap) {
    if (!place) return;
    selectedSlug = place.slug;
    document.querySelectorAll('.place-card.selected').forEach(card => card.classList.remove('selected'));
    const card = document.querySelector(`.place-card[data-slug="${place.slug}"]`);
    if (card) {
      card.classList.add('selected');
      if (fromMap && !mobileMapMedia.matches) card.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
    const distance = userLocation && place.distance != null ? ` · a ${formatDistance(place.distance)}` : '';
    panelContent.innerHTML = `<div class="panel-type" style="--type-color:${place.color}">${escapeHtml(place.typeLabel)}${distance}</div><h2>${escapeHtml(place.name)}</h2><p class="panel-address">${escapeHtml(place.district)} · ${escapeHtml(place.address)}</p>${panelSchedule(place)}<div class="panel-actions"><a href="/${place.slug}">Ver ficha</a><a class="secondary" href="${directionsUrl(place)}" target="_blank" rel="noopener noreferrer">Cómo llegar</a><a class="secondary" href="${escapeHtml(place.web)}" rel="noopener noreferrer">Web oficial</a></div>`;
    panel.hidden = false;
    panel.classList.add('open');
    map.invalidateSize({ pan: false });
    const marker = markers.get(place.slug);
    if (marker) {
      clusters.zoomToShowLayer(marker, () => {
        markSelectedMarker(place.slug);
        map.setView(marker.getLatLng(), Math.max(map.getZoom(), 15), { animate: true });
      });
    }
    // En el móvil el mapa queda arriba: si se pulsa una tarjeta del listado, se sube a verlo.
    // En escritorio, mapa y listado miden lo que la ventana: si la ficha asoma por debajo,
    // se baja hasta que el bloque entero quede a la vista.
    if (mobileMapMedia.matches) {
      if (!fromMap) mapColumn.scrollIntoView({ behavior: 'smooth', block: 'start' });
    } else if (panel.getBoundingClientRect().bottom > window.innerHeight) {
      mapColumn.closest('main').scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
    if (push && location.hash !== `#${place.slug}`) history.pushState({ landingSlug: place.slug }, '', `#${place.slug}`);
  }

  function closePanel() {
    selectedSlug = null;
    panel.classList.remove('open');
    panel.hidden = true;
    map.invalidateSize({ pan: false });
    markSelectedMarker(null);
    document.querySelectorAll('.place-card.selected').forEach(card => card.classList.remove('selected'));
  }

  results.addEventListener('click', event => {
    if (event.target.closest('a')) return;
    const card = event.target.closest('.place-card');
    if (card) openPanel(data.places.find(place => place.slug === card.dataset.slug), true);
  });
  results.addEventListener('keydown', event => {
    if (event.key !== 'Enter' && event.key !== ' ') return;
    const card = event.target.closest('.place-card');
    if (card && !event.target.closest('a')) { event.preventDefault(); openPanel(data.places.find(place => place.slug === card.dataset.slug), true); }
  });
  panelClose.addEventListener('click', () => {
    if (history.state && history.state.landingSlug) history.back();
    else { closePanel(); history.replaceState({}, '', location.pathname); }
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && panel.classList.contains('open')) panelClose.click();
  });
  window.addEventListener('popstate', () => {
    const slug = location.hash.slice(1);
    if (slug) openPanel(data.places.find(place => place.slug === slug), false, true);
    else closePanel();
  });

  if (filters) filters.addEventListener('click', event => {
    const button = event.target.closest('button[data-filter]');
    if (!button) return;
    activeFilter = button.dataset.filter;
    filters.querySelectorAll('button').forEach(item => item.classList.toggle('active', item === button));
    applyWeekendFilter(true);
  });

  const initialSlug = location.hash.slice(1);
  const start = data.mode === 'weekend' ? loadWeekend() : loadFullDay();
  start.finally(() => {
    if (initialSlug) openPanel(data.places.find(place => place.slug === initialSlug), false, true);
    setTimeout(() => map.invalidateSize(), 0);
    // Si ya dio permiso en otra visita, se ordena por cercanía sin preguntar ni mover el mapa.
    if (navigator.geolocation && navigator.permissions && navigator.permissions.query) {
      navigator.permissions.query({ name: 'geolocation' }).then(permission => {
        if (permission.state !== 'granted') return;
        navigator.geolocation.getCurrentPosition(position => useLocation(position, false), () => {}, { maximumAge: 5 * 60 * 1000, timeout: 5000 });
      }).catch(() => {});
    }
  });
})();
