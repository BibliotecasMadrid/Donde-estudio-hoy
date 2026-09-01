/*
 * Resolver del calendario diario publicado.
 *
 * Los JSON de /horarios/ se generan con build.py. Esta capa sólo busca
 * slug + fecha y evalúa la hora actual en Europe/Madrid; no interpreta
 * nunca el texto editorial `lugares[].horario`.
 */
(function (global) {
  'use strict';

  const TIME_ZONE = 'Europe/Madrid';
  const monthCache = new Map();
  const monthPromises = new Map();
  const partFormatter = new Intl.DateTimeFormat('en-CA', {
    timeZone: TIME_ZONE,
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hourCycle: 'h23'
  });
  const dateFormatter = new Intl.DateTimeFormat('es-ES', {
    timeZone: TIME_ZONE,
    weekday: 'short', day: 'numeric', month: 'short'
  });

  function madridParts(date) {
    const values = {};
    for (const part of partFormatter.formatToParts(date || new Date())) {
      if (part.type !== 'literal') values[part.type] = part.value;
    }
    return {
      year: Number(values.year),
      month: Number(values.month),
      day: Number(values.day),
      hour: Number(values.hour),
      minute: Number(values.minute)
    };
  }

  function keyFromParts(parts) {
    return `${parts.year}-${String(parts.month).padStart(2, '0')}-${String(parts.day).padStart(2, '0')}`;
  }

  function dateKey(date) {
    return keyFromParts(madridParts(date));
  }

  function partsFromKey(key) {
    const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(key || '');
    if (!match) throw new Error(`Fecha de calendario inválida: ${key}`);
    return { year: Number(match[1]), month: Number(match[2]), day: Number(match[3]) };
  }

  function addDays(key, count) {
    const parts = partsFromKey(key);
    const utc = new Date(Date.UTC(parts.year, parts.month - 1, parts.day + count));
    return `${utc.getUTCFullYear()}-${String(utc.getUTCMonth() + 1).padStart(2, '0')}-${String(utc.getUTCDate()).padStart(2, '0')}`;
  }

  function weekendKeys(date) {
    const today = dateKey(date || new Date());
    const parts = partsFromKey(today);
    const weekday = new Date(Date.UTC(parts.year, parts.month - 1, parts.day, 12)).getUTCDay();
    const saturdayOffset = weekday === 6 ? 0 : weekday === 0 ? -1 : 6 - weekday;
    const saturday = addDays(today, saturdayOffset);
    return { saturday, sunday: addDays(saturday, 1) };
  }

  function monthId(year, month) {
    return `${year}-${String(month).padStart(2, '0')}`;
  }

  function monthUrl(year, month) {
    return `horarios/${monthId(year, month)}.json`;
  }

  function ensureMonth(year, month) {
    const id = monthId(year, month);
    if (monthCache.has(id)) return Promise.resolve(monthCache.get(id));
    if (monthPromises.has(id)) return monthPromises.get(id);
    const promise = fetch(monthUrl(year, month), { cache: 'no-store' })
      .then(response => {
        if (!response.ok) throw new Error(`No se pudo cargar ${monthUrl(year, month)}`);
        return response.json();
      })
      .then(data => {
        if (data.year !== year || data.month !== month || !data.places) {
          throw new Error(`Calendario mensual inválido: ${id}`);
        }
        monthCache.set(id, data);
        monthPromises.delete(id);
        return data;
      })
      .catch(error => {
        monthPromises.delete(id);
        throw error;
      });
    monthPromises.set(id, promise);
    return promise;
  }

  function getEntry(slug, keyOrDate) {
    const key = typeof keyOrDate === 'string' ? keyOrDate : dateKey(keyOrDate);
    const parts = partsFromKey(key);
    const data = monthCache.get(monthId(parts.year, parts.month));
    return data && data.places && data.places[slug] ? data.places[slug][parts.day - 1] || null : null;
  }

  async function getEntryAsync(slug, keyOrDate) {
    const key = typeof keyOrDate === 'string' ? keyOrDate : dateKey(keyOrDate);
    const parts = partsFromKey(key);
    await ensureMonth(parts.year, parts.month);
    return getEntry(slug, key);
  }

  async function getWeek(slug, fromDate, count) {
    const start = typeof fromDate === 'string' ? fromDate : dateKey(fromDate);
    const keys = Array.from({ length: count || 7 }, (_, index) => addDays(start, index));
    await Promise.all([...new Set(keys.map(key => {
      const parts = partsFromKey(key);
      return monthId(parts.year, parts.month);
    }))].map(id => {
      const [year, month] = id.split('-').map(Number);
      return ensureMonth(year, month);
    }));
    return keys.map(key => ({ key, entry: getEntry(slug, key) }));
  }

  function minutes(value) {
    const match = /^(\d{1,2}):(\d{2})$/.exec(value || '');
    return match ? Number(match[1]) * 60 + Number(match[2]) : null;
  }

  function isOpen(entry, date) {
    if (!entry || entry.estado !== 'abierto') return false;
    const current = madridParts(date || new Date());
    const now = current.hour * 60 + current.minute;
    return (entry.intervalos || []).some(([start, end]) => {
      const from = minutes(start);
      const to = minutes(end);
      return from !== null && to !== null && now >= from && now < to;
    });
  }

  function formatIntervals(intervals) {
    if (!intervals || intervals.length === 0) return '';
    if (intervals.length === 1 && intervals[0][0] === '00:00' && intervals[0][1] === '24:00') return '24 h';
    return intervals.map(([start, end]) => `${start}–${end}h`).join(' y ');
  }

  function dayLabel(key) {
    const parts = partsFromKey(key);
    // Al mediodía UTC el día siempre coincide con el de Madrid, incluso con DST.
    const reference = new Date(Date.UTC(parts.year, parts.month - 1, parts.day, 12));
    const values = {};
    for (const part of dateFormatter.formatToParts(reference)) {
      if (part.type !== 'literal') values[part.type] = part.value.replace(/\.$/, '');
    }
    const capitalise = value => value ? value.charAt(0).toUpperCase() + value.slice(1) : '';
    return `${capitalise(values.weekday)} ${values.day} ${capitalise(values.month)}`;
  }

  function displayFor(entry, key, now) {
    const today = key === dateKey(now || new Date());
    if (!entry) {
      return { statusText: 'Consultar', statusClass: 'status-info', isOpen: null, hoursText: 'Horario no disponible', today };
    }
    if (entry.estado === 'consultar') {
      return { statusText: 'Consultar', statusClass: 'status-info', isOpen: null, hoursText: entry.nota || 'Consultar horario', today };
    }
    if (entry.estado === 'cerrado') {
      return { statusText: 'Cerrado', statusClass: 'status-closed', isOpen: false, hoursText: entry.nota || 'Cerrado', today };
    }
    const opened = today ? isOpen(entry, now || new Date()) : null;
    const hours = formatIntervals(entry.intervalos);
    return {
      statusText: opened === null ? 'Horario' : (opened ? 'Abierto' : 'Cerrado'),
      statusClass: opened === null ? 'status-info' : (opened ? 'status-open' : 'status-closed'),
      isOpen: opened,
      hoursText: entry.nota ? `${hours} · ${entry.nota}` : hours,
      today
    };
  }

  function renderToday(slug, elements, now) {
    const reference = now || new Date();
    const key = dateKey(reference);
    const title = elements && elements.title;
    const badge = elements && elements.badge;
    const hours = elements && elements.hours;
    if (title) title.textContent = `HOY · ${dayLabel(key)}`;
    return getEntryAsync(slug, key).then(entry => {
      const shown = displayFor(entry, key, reference);
      if (badge) {
        badge.className = `status-badge ${shown.statusClass}`;
        badge.textContent = shown.statusText;
      }
      if (hours) hours.textContent = shown.hoursText;
      return shown;
    }).catch(() => {
      if (badge) {
        badge.className = 'status-badge status-info';
        badge.textContent = 'Consultar';
      }
      if (hours) hours.textContent = 'No se pudo cargar el calendario';
      return null;
    });
  }

  function renderWeek(slug, container, count, now) {
    if (!container) return Promise.resolve([]);
    const reference = now || new Date();
    const today = dateKey(reference);
    container.textContent = 'Cargando calendario…';
    return getWeek(slug, reference, count || 7).then(days => {
      const heading = document.createElement('div');
      heading.className = 'panel-label panel-calendar-week-label';
      heading.style.cssText = 'margin-top:8px; margin-bottom:4px; font-size:9.5px;';
      heading.textContent = `Próximos ${days.length} días`;
      const table = document.createElement('table');
      table.className = 'panel-week-table';
      const body = document.createElement('tbody');
      for (const { key, entry } of days) {
        const row = document.createElement('tr');
        row.dataset.calendarDate = key;
        if (key === today) row.className = 'day-row-today';
        const day = document.createElement('td');
        day.textContent = `${dayLabel(key)}${key === today ? ' (Hoy)' : ''}`;
        if (entry && entry.nota) day.title = entry.nota;
        const hours = document.createElement('td');
        hours.className = 'day-hours';
        hours.textContent = entry ? (entry.estado === 'abierto' ? formatIntervals(entry.intervalos) : entry.estado === 'consultar' ? 'Consultar' : 'Cerrado') : 'Consultar';
        row.append(day, hours);
        body.appendChild(row);
      }
      table.appendChild(body);
      container.replaceChildren(heading, table);
      return days;
    }).catch(() => {
      container.textContent = 'No se pudo cargar el calendario.';
      return [];
    });
  }

  global.Horarios = Object.freeze({
    timeZone: TIME_ZONE,
    madridParts,
    dateKey,
    addDays,
    weekendKeys,
    ensureMonth,
    getEntry,
    getEntryAsync,
    getWeek,
    isOpen,
    formatIntervals,
    dayLabel,
    displayFor,
    renderToday,
    renderWeek
  });
})(window);
