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
  let activeFilter = 'all';
  let visiblePlaces = [...data.places];

  const escapeHtml = value => String(value == null ? '' : value)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#039;');

  const map = L.map('map', { center: [40.4168, -3.7038], zoom: 11 });
  window.Basemap.add(map);
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
    marker.on('click', () => openPanel(place, true));
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
    return `<article class="place-card" data-slug="${place.slug}" tabindex="0">
      <div class="card-top"><span class="type-badge" style="--type-color:${place.color}">${escapeHtml(place.typeLabel)}</span>${status}</div>
      <h3>${escapeHtml(place.name)}</h3><p>${escapeHtml(place.district)} · ${escapeHtml(place.address)}</p>
      <div class="card-schedule">${schedule}</div><a class="detail-link" href="/${place.slug}">Ver ficha y próximos horarios</a>
    </article>`;
  }

  function sortPlaces(places) {
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

  function openPanel(place, push) {
    if (!place) return;
    document.querySelectorAll('.place-card.selected').forEach(card => card.classList.remove('selected'));
    const card = document.querySelector(`.place-card[data-slug="${place.slug}"]`);
    if (card) card.classList.add('selected');
    panelContent.innerHTML = `<div class="panel-type">${escapeHtml(place.typeLabel)}</div><h2>${escapeHtml(place.name)}</h2><p class="panel-address">${escapeHtml(place.district)} · ${escapeHtml(place.address)}</p>${panelSchedule(place)}<div class="panel-actions"><a href="/${place.slug}">Ver ficha completa</a><a class="secondary" href="${escapeHtml(place.web)}" rel="noopener noreferrer">Web oficial</a></div>`;
    panel.classList.add('open');
    panel.setAttribute('aria-hidden', 'false');
    const marker = markers.get(place.slug);
    if (marker) map.setView(marker.getLatLng(), Math.max(map.getZoom(), 14), { animate: true });
    if (push && location.hash !== `#${place.slug}`) history.pushState({ landingSlug: place.slug }, '', `#${place.slug}`);
  }

  function closePanel() {
    panel.classList.remove('open');
    panel.setAttribute('aria-hidden', 'true');
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
  window.addEventListener('popstate', () => {
    const slug = location.hash.slice(1);
    if (slug) openPanel(data.places.find(place => place.slug === slug), false);
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
    if (initialSlug) openPanel(data.places.find(place => place.slug === initialSlug), false);
    setTimeout(() => map.invalidateSize(), 0);
  });
})();
