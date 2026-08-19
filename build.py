#!/usr/bin/env python3
"""
build.py - Generador estático para "Dónde estudiar en Madrid".

Lee el array `lugares` de index.html y genera:
  1. Un archivo <slug>.html para cada centro (ej. clara-campoamor.html).
  2. sitemap.xml con la home + todos los centros.

Uso:
  python build.py
"""

import json
import re
import os
import html
import unicodedata
from urllib.parse import quote_plus

BASE = "https://bibliotecasmadrid.github.io/Donde-estudio-hoy/"
LASTMOD = "2026-08-19"

PREFIJOS = [
    "biblioteca pública ",
    "biblioteca municipal ",
    "salas de estudio ",
    "sala de estudio del ",
    "sala de estudio de la ",
    "sala de estudio ",
    "sala de lectura ",
    "biblioteca ",
]

COLORES = {
    "biblioteca": {"fill": "#2563EB", "label": "Biblioteca"},
    "sala":       {"fill": "#059669", "label": "Sala de estudio"},
    "universidad":{"fill": "#7C3AED", "label": "Biblioteca universitaria"},
}

CALENDARIO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "calendario.json")
if os.path.exists(CALENDARIO_PATH):
    with open(CALENDARIO_PATH, "r", encoding="utf-8") as f:
        CALENDARIO = json.load(f)
else:
    CALENDARIO = {"holidays": {}, "places_exceptions": {}}


def slugify(nombre):
    base = nombre
    low = nombre.lower()
    for p in PREFIJOS:
        if low.startswith(p):
            base = nombre[len(p):]
            break
    base = unicodedata.normalize("NFKD", base)
    base = "".join(c for c in base if not unicodedata.combining(c)).lower()
    base = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
    return base or "centro"


def unique_slugs(lugares):
    seen = {}
    out = []
    for d in lugares:
        s = slugify(d["nombre"])
        if s in seen:
            seen[s] += 1
            s = f"{s}-{seen[s]}"
        else:
            seen[s] = 1
        out.append(s)
    return out


def extract_lugares(index_html):
    src = open(index_html, encoding="utf-8").read()
    i = src.index("const lugares = [")
    arr_start = src.index("[", i)
    end = src.index("\n];", arr_start)
    body = src[arr_start + 1:end]
    body = "\n".join(ln for ln in body.split("\n") if not ln.strip().startswith("//"))
    body = re.sub(r'(?<![\w"])(tipo|nombre|distrito|direccion|lat|lng|plazas|foto|horario|web|libcal_lid|libcal_iid)\s*:',
                  r'"\1":', body)
    jtext = "[" + body + "]"
    jtext = re.sub(r",(\s*[}\]])", r"\1", jtext)
    return json.loads(jtext)


def web_url(d):
    if d.get("web"):
        return d["web"], "Web oficial"
    return "https://www.google.com/search?q=" + quote_plus(d["nombre"] + " Madrid"), "Buscar web y horario"


def get_today_info(d, slug, now=None):
    if now is None:
        import datetime
        now = datetime.datetime.now()
    day = (now.weekday() + 1) % 7
    month = now.month
    day_of_month = now.day
    year = now.year
    current_minutes = now.hour * 60 + now.minute
    
    mm = f"{month:02d}"
    dd = f"{day_of_month:02d}"
    date_key = f"{year}-{mm}-{dd}"
    month_day = f"{mm}-{dd}"
    
    days_names = ['domingo', 'lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado']
    month_names = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']
    
    day_name_cap = days_names[day].capitalize()
    date_formatted = f"{day_name_cap}, {day_of_month} de {month_names[month-1]}"
    
    exceptions = CALENDARIO.get("places_exceptions", {}).get(slug, {})
    h = d["horario"].lower()
    
    if 'consultar' in h or 'teléfono' in h or 'telefono' in h:
        return {
            'date_formatted': date_formatted,
            'status_text': 'Consultar',
            'status_class': 'status-info',
            'today_schedule': 'Consultar horario por teléfono',
            'is_open': None
        }
        
    def parse_intervals(text):
        intervals = []
        for m in re.finditer(r'(\d{1,2})(?::(\d{2}))?\s*[–\-—a]\s*(\d{1,2})(?::(\d{2}))?h?', text, re.IGNORECASE):
            sh = int(m.group(1))
            sm = int(m.group(2)) if m.group(2) else 0
            eh = int(m.group(3))
            em = int(m.group(4)) if m.group(4) else 0
            intervals.append({
                'start_min': sh * 60 + sm,
                'end_min': eh * 60 + em,
                'start_str': f"{sh}:{sm:02d}",
                'end_str': f"{eh}:{em:02d}"
            })
        return intervals

    if CALENDARIO.get("holidays", {}).get(date_key):
        holiday_name = CALENDARIO["holidays"][date_key]
        if not ('festivos' in h and 'festivos cerrado' not in h and 'cerrado sáb, dom y festivos' not in h and 'festivos, cerrado' not in h):
            return {
                'date_formatted': date_formatted,
                'status_text': 'Cerrado',
                'status_class': 'status-closed',
                'today_schedule': f"Cerrado por festivo ({holiday_name})",
                'is_open': False
            }

    if "summer_closure" in exceptions:
        sc = exceptions["summer_closure"]
        if sc["start"] <= month_day <= sc["end"]:
            return {
                'date_formatted': date_formatted,
                'status_text': 'Cerrado',
                'status_class': 'status-closed',
                'today_schedule': 'Cerrado por vacaciones de verano',
                'is_open': False
            }

    if "august_schedule" in exceptions:
        aug = exceptions["august_schedule"]
        if aug["closure_start"] <= month_day <= aug["closure_end"]:
            return {
                'date_formatted': date_formatted,
                'status_text': 'Cerrado',
                'status_class': 'status-closed',
                'today_schedule': 'Cerrado por periodo estival',
                'is_open': False
            }
        elif aug["reduced_start"] <= month_day <= aug["reduced_end"]:
            if 1 <= day <= 5:
                ivs = parse_intervals(aug["reduced_schedule"])
                is_open = any(iv['start_min'] <= current_minutes < iv['end_min'] for iv in ivs)
                return {
                    'date_formatted': date_formatted,
                    'status_text': 'Abierto' if is_open else 'Cerrado',
                    'status_class': 'status-open' if is_open else 'status-closed',
                    'today_schedule': aug["reduced_schedule"] + ' (Horario de agosto)',
                    'is_open': is_open
                }
            else:
                return {
                    'date_formatted': date_formatted,
                    'status_text': 'Cerrado',
                    'status_class': 'status-closed',
                    'today_schedule': 'Cerrado los fines de semana de agosto',
                    'is_open': False
                }

    if "summer_period" in exceptions:
        sp = exceptions["summer_period"]
        if sp["start"] <= month_day <= sp["end"]:
            if 1 <= day <= 5:
                ivs = parse_intervals(sp["weekday_schedule"])
                is_open = any(iv['start_min'] <= current_minutes < iv['end_min'] for iv in ivs)
                return {
                    'date_formatted': date_formatted,
                    'status_text': 'Abierto' if is_open else 'Cerrado',
                    'status_class': 'status-open' if is_open else 'status-closed',
                    'today_schedule': sp["weekday_schedule"] + ' (Horario de verano)',
                    'is_open': is_open
                }

    lines = d["horario"].split('\n')
    main_line = lines[0]
    
    if day == 0:
        if any(k in h for k in ['dom', 'fines de semana', 'lun–dom', 'lun-dom']):
            sunday_text = ''
            if 'sáb–dom' in h or 'sab-dom' in h or 'sáb y dom' in h:
                m = re.search(r'S[áa]b[–\-—]Dom\s+([^\n·]+)', d["horario"], re.IGNORECASE)
                if m: sunday_text = m.group(1)
            elif 'fines de semana' in h:
                m = re.search(r'Fines de semana[^\d]*(\d[^\n·]+)', d["horario"], re.IGNORECASE)
                if m: sunday_text = m.group(1)
            elif 'dom' in h and 'cerrado' not in h:
                m = re.search(r'Dom\s+([^\n·]+)', d["horario"], re.IGNORECASE)
                if m: sunday_text = m.group(1)
            elif 'lun–dom' in h or 'lun-dom' in h:
                sunday_text = main_line
                
            if sunday_text:
                intervals = parse_intervals(sunday_text)
                if intervals:
                    is_open = any(iv['start_min'] <= current_minutes < iv['end_min'] for iv in intervals)
                    sched_formatted = ' y '.join(f"{iv['start_str']}–{iv['end_str']}h" for iv in intervals)
                    return {
                        'date_formatted': date_formatted,
                        'status_text': 'Abierto' if is_open else 'Cerrado',
                        'status_class': 'status-open' if is_open else 'status-closed',
                        'today_schedule': sched_formatted,
                        'is_open': is_open
                    }
        return {
            'date_formatted': date_formatted,
            'status_text': 'Cerrado',
            'status_class': 'status-closed',
            'today_schedule': 'Cerrado hoy',
            'is_open': False
        }
        
    if day == 6:
        if any(k in h for k in ['sáb', 'sab', 'fines de semana', 'lun–dom', 'lun-dom', 'lun–sáb', 'lun-sab']):
            sab_text = ''
            if 'sáb–dom' in h or 'sab-dom' in h or 'sáb y dom' in h:
                m = re.search(r'S[áa]b[–\-—]Dom\s+([^\n·]+)', d["horario"], re.IGNORECASE)
                if m: sab_text = m.group(1)
            elif 'sáb' in h or 'sab' in h:
                m = re.search(r'S[áa]b\s+([^\n·\(\)]+)', d["horario"], re.IGNORECASE)
                if m: sab_text = m.group(1)
            elif 'fines de semana' in h:
                m = re.search(r'Fines de semana[^\d]*(\d[^\n·\(\)]+)', d["horario"], re.IGNORECASE)
                if m: sab_text = m.group(1)
            elif any(k in h for k in ['lun–sáb', 'lun-sab', 'lun–dom', 'lun-dom']):
                sab_text = main_line
                
            if sab_text:
                intervals = parse_intervals(sab_text)
                if intervals:
                    is_open = any(iv['start_min'] <= current_minutes < iv['end_min'] for iv in intervals)
                    sched_formatted = ' y '.join(f"{iv['start_str']}–{iv['end_str']}h" for iv in intervals)
                    return {
                        'date_formatted': date_formatted,
                        'status_text': 'Abierto' if is_open else 'Cerrado',
                        'status_class': 'status-open' if is_open else 'status-closed',
                        'today_schedule': sched_formatted,
                        'is_open': is_open
                    }
        return {
            'date_formatted': date_formatted,
            'status_text': 'Cerrado',
            'status_class': 'status-closed',
            'today_schedule': 'Cerrado hoy',
            'is_open': False
        }
        
    weekday_part = main_line.split('·')[0] if '·' in main_line else main_line
    intervals = parse_intervals(weekday_part)
    if intervals:
        is_open = any(iv['start_min'] <= current_minutes < iv['end_min'] for iv in intervals)
        sched_formatted = ' y '.join(f"{iv['start_str']}–{iv['end_str']}h" for iv in intervals)
        return {
            'date_formatted': date_formatted,
            'status_text': 'Abierto' if is_open else 'Cerrado',
            'status_class': 'status-open' if is_open else 'status-closed',
            'today_schedule': sched_formatted,
            'is_open': is_open
        }
        
    return {
        'date_formatted': date_formatted,
        'status_text': 'Abierto',
        'status_class': 'status-open',
        'today_schedule': main_line,
        'is_open': True
    }




def page_html(d, slug):
    c = COLORES[d["tipo"]]
    e = html.escape
    today = get_today_info(d, slug)
    horario_inline = d["horario"].replace("\n", " ")
    horario_html = "".join(f"<div>{e(l)}</div>" for l in d["horario"].split("\n"))
    web, web_label = web_url(d)
    desc = f'{d["nombre"]}: {d["direccion"]}. Horario: {horario_inline}. {c["label"]} en Madrid.'
    canonical = BASE + slug
    
    # Street View perspective (default yaw calculation or frontal heading)
    lat, lng = d["lat"], d["lng"]
    streetview_url = f"https://maps.google.com/maps?q=&layer=c&cbll={lat},{lng}&cbp=11,0,0,0,0&output=svembed"
    maps_sv_link = f"https://www.google.com/maps/@{lat},{lng},3a,70.2y,0h,80t/data=!3m7!1e1!3m5!1e0!5m1!1e4"

    ld = {
        "@context": "https://schema.org",
        "@type": "Library",
        "name": d["nombre"],
        "description": "Horario: " + horario_inline,
        "address": {
            "@type": "PostalAddress",
            "streetAddress": d["direccion"],
            "addressLocality": "Madrid",
        "addressRegion": "Comunidad de Madrid",
            "addressCountry": "ES",
        },
        "geo": {"@type": "GeoCoordinates", "latitude": lat, "longitude": lng},
        "maximumAttendeeCapacity": d.get("plazas", 100),
        "url": canonical,
        "areaServed": "Madrid",
    }
    if d.get("foto"):
        ld["image"] = d["foto"]

    live_tag_html = """
          <div class="panel-live-tag" title="Sincronizado en tiempo real con BiblioAgenda UAM">
            <svg viewBox="0 0 24 24"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>
            En directo · BiblioAgenda UAM
          </div>""" if d.get("libcal_lid") else ""
    week_container_html = '<div id="panel-uam-week" class="panel-live-week"></div>' if d.get("libcal_lid") else ""

    d_json = json.dumps(d, ensure_ascii=False)
    cal_json_esc = json.dumps(json.dumps(CALENDARIO, ensure_ascii=False))
    og_img = d.get("foto", "https://bibliotecasmadrid.github.io/Donde-estudio-hoy/icons/icon-512.png")

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="theme-color" content="#2563EB">
  <link rel="manifest" href="manifest.json">
  <link rel="apple-touch-icon" href="icons/apple-touch-icon.png">
  <link rel="icon" type="image/png" sizes="64x64" href="icons/favicon-64.png">
  <title>{e(d["nombre"])} · Horario y dirección · Madrid</title>
  <meta name="description" content="{e(desc)}">
  <link rel="canonical" href="{e(canonical)}">
  <meta name="robots" content="index, follow">
  <meta property="og:type" content="article">
  <meta property="og:locale" content="es_ES">
  <meta property="og:title" content="{e(d["nombre"])} · Horario y dirección">
  <meta property="og:description" content="{e(desc)}">
  <meta property="og:url" content="{e(canonical)}">
  <meta property="og:image" content="{e(og_img)}">
  <script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>
  <style>
    :root {{ --ink:#1A1F36; --ink-2:#5A6172; --ink-3:#9AA0AE; --line:#ECEEF2; }}
    * {{ margin:0; padding:0; box-sizing:border-box; }}
    html, body {{
      width:100%; height:100%; overflow:hidden;
      font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;
      -webkit-font-smoothing:antialiased; color:var(--ink);
    }}
    
    /* ── Fondo Street View 1:1 a pantalla completa sin zoom ── */
    .bg-streetview {{
      position: fixed;
      inset: 0;
      width: 100vw;
      height: 100vh;
      z-index: 1;
      background: #0f172a;
    }}
    .bg-streetview iframe {{
      width: 100%;
      height: 100%;
      border: 0;
      display: block;
    }}
    
        
    /* ── Tarjeta flotante horizontal centrada abajo ── */
    .card {{
      position: fixed;
      bottom: 24px;
      left: 50%;
      transform: translateX(-50%);
      max-width: 860px;
      width: calc(100% - 48px);
      max-height: calc(100vh - 48px);
      overflow-y: auto;
      background: rgba(255, 255, 255, 0.95);
      backdrop-filter: blur(24px);
      -webkit-backdrop-filter: blur(24px);
      border: 1px solid rgba(255, 255, 255, 0.8);
      border-radius: 24px;
      padding: 22px 28px 20px;
      box-shadow: 0 24px 50px rgba(0,0,0,0.28), 0 4px 12px rgba(0,0,0,0.08);
      z-index: 10;
    }}
    
    .card-header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 12px;
    }}
    .back {{
      display: inline-flex;
      align-items: center;
      gap: 5px;
      font-size: 13px;
      font-weight: 600;
      color: var(--ink-2);
      text-decoration: none;
      transition: color .12s;
    }}
    .back:hover {{ color: var(--ink); }}
    .badge {{
      display: inline-block;
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      padding: 3px 10px;
      border-radius: 999px;
      color: #fff;
      background: {c["fill"]};
    }}
    
    .card-grid {{
      display: grid;
      grid-template-columns: 1.2fr 1fr;
      gap: 28px;
      align-items: start;
    }}
    
    h1 {{
      font-size: 21px;
      font-weight: 800;
      letter-spacing: -0.01em;
      line-height: 1.25;
      margin-bottom: 6px;
    }}
    .addr {{
      font-size: 13.5px;
      color: var(--ink-2);
      line-height: 1.45;
      margin-bottom: 12px;
    }}
    
    .capacity-tag {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      font-size: 12.5px;
      font-weight: 600;
      color: var(--ink-2);
      background: #F1F3F7;
      padding: 6px 12px;
      border-radius: 10px;
      margin-bottom: 16px;
    }}
    .capacity-tag svg {{
      color: var(--ink-3);
      flex-shrink: 0;
    }}

    /* ── Box HOY ───────────────────────────── */
    .today-card {{
      background: #F8FAFC;
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 12px 14px;
      margin-bottom: 12px;
    }}
    .today-head {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 4px;
    }}
    .today-title {{
      font-size: 10.5px;
      font-weight: 800;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--ink-2);
    }}
    .status-badge {{
      display: inline-flex;
      align-items: center;
      gap: 5px;
      font-size: 11.5px;
      font-weight: 700;
      padding: 3px 9px;
      border-radius: 999px;
    }}
    .status-badge.status-open {{
      background: #DCFCE7;
      color: #15803D;
    }}
    .status-badge.status-open::before {{
      content: "";
      display: inline-block;
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background: #16A34A;
    }}
    .status-badge.status-closed {{
      background: #FEE2E2;
      color: #B91C1C;
    }}
    .status-badge.status-closed::before {{
      content: "";
      display: inline-block;
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background: #DC2626;
    }}
    .status-badge.status-info {{
      background: #E0F2FE;
      color: #0369A1;
    }}
    .today-hours {{
      font-size: 13.5px;
      font-weight: 700;
      color: var(--ink);
    }}
    .panel-live-tag {{
      display: inline-flex;
      align-items: center;
      gap: 5px;
      font-size: 10px;
      font-weight: 700;
      color: #0369A1;
      background: #E0F2FE;
      padding: 3px 8px;
      border-radius: 6px;
      margin-top: 6px;
    }}
    .panel-live-tag svg {{
      width: 10px;
      height: 10px;
      fill: #0284C7;
      flex-shrink: 0;
    }}
    .panel-live-week {{
      margin-top: 10px;
      padding-top: 8px;
      border-top: 1px dashed var(--line);
    }}
    .panel-week-table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 11.5px;
      margin-top: 4px;
    }}
    .panel-week-table td {{
      padding: 2.5px 2px;
      color: var(--ink-2);
    }}
    .panel-week-table tr.day-row-today td {{
      font-weight: 700;
      color: #1D4ED8;
    }}
    .panel-week-table td.day-hours {{
      text-align: right;
      font-weight: 600;
      color: var(--ink);
    }}
    .panel-week-table tr.day-row-today td.day-hours {{
      color: #1D4ED8;
    }}

    .sched h2 {{ font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.07em; color: var(--ink-3); margin-bottom: 4px; }}
    .sched {{ font-size:13px; line-height:1.55; border-top:1px solid var(--line); padding-top:10px; }}
    .actions {{ display:flex; flex-wrap:wrap; gap:8px; margin-top:14px; }}
    .btn {{
      display:inline-flex; align-items:center; gap:6px; font-size:12.5px; font-weight:600;
      text-decoration:none; padding:8px 14px; border-radius:999px; transition:filter .12s ease;
    }}
    .btn-primary {{ background:{c["fill"]}; color:#fff; }}
    .btn-primary:hover {{ filter:brightness(1.08); }}
    .btn-ghost {{ background:#F1F3F7; color:var(--ink); }}
    .btn-ghost:hover {{ background:#E7EAF0; }}
    footer {{ margin-top:14px; font-size:10px; color:var(--ink-3); line-height:1.4; }}
    footer a {{ color:var(--ink-3); }}
    
    @media (max-width: 768px) {{
      .card {{
        bottom: 16px;
        padding: 20px 18px 16px;
        width: calc(100% - 32px);
        max-height: 80vh;
      }}
      .card-grid {{
        grid-template-columns: 1fr;
        gap: 16px;
      }}
    }}
  </style>
</head>
<body>
  <!-- Fondo Google Street View a tamaño natural 1:1 -->
  <div class="bg-streetview">
    <iframe src="{streetview_url}" allowfullscreen loading="lazy"></iframe>
  </div>
  

  <!-- Tarjeta horizontal centrada abajo -->
  <main class="card">
    <div class="card-header">
      <a class="back" href="./">← Volver al mapa</a>
      <span class="badge">{e(c["label"])}</span>
    </div>
    
    <div class="card-grid">
      <div class="card-main-col">
        <h1>{e(d["nombre"])}</h1>
        <p class="addr">{e(d["distrito"])} · {e(d["direccion"])}</p>
        
        <div class="capacity-tag">
          <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
          <span>{d.get("plazas", 100)} puestos de estudio</span>
        </div>

        <div class="actions">
          <a class="btn btn-primary" href="./#{slug}">Ver en el mapa</a>
          <a class="btn btn-ghost" href="{e(web)}" target="_blank" rel="noopener noreferrer">{e(web_label)} ↗</a>
          <a class="btn btn-ghost" href="{maps_sv_link}" target="_blank" rel="noopener noreferrer">Street View 360° ↗</a>
        </div>
      </div>

      <div class="card-side-col">
        <div class="today-card" id="today-card">
          <div class="today-head">
            <span class="today-title" id="today-title">HOY · {today['date_formatted']}</span>
            <span class="status-badge {today['status_class']}" id="status-badge">{today['status_text']}</span>
          </div>
          <div class="today-hours" id="today-hours">{today['today_schedule']}</div>
          {live_tag_html}
          {week_container_html}
        </div>

        <div class="sched">
          <h2>Horario habitual</h2>
          {horario_html}
        </div>
        
        <footer>
          Datos: <a href="https://datos.madrid.es" target="_blank" rel="noopener">datos.madrid.es</a> (CC BY 4.0).
        </footer>
      </div>
    </div>
  </main>

  <script>
  (function() {{
    const d = {d_json};
    const slug = "{slug}";
    const CALENDARIO = JSON.parse({cal_json_esc});
    
    function updateToday() {{
      const date = new Date();
      const day = date.getDay();
      const month = date.getMonth();
      const dayOfMonth = date.getDate();
      const year = date.getFullYear();
      const currentMinutes = date.getHours() * 60 + date.getMinutes();
      
      const mm = String(month + 1).padStart(2, '0');
      const dd = String(dayOfMonth).padStart(2, '0');
      const dateKey = `${{year}}-${{mm}}-${{dd}}`;
      const monthDay = `${{mm}}-${{dd}}`;
      
      const daysNames = ['domingo', 'lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado'];
      const monthNames = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];
      const dayNameCap = daysNames[day].charAt(0).toUpperCase() + daysNames[day].slice(1);
      const dateFormatted = `${{dayNameCap}}, ${{dayOfMonth}} de ${{monthNames[month]}}`;
      
      const titleEl = document.getElementById('today-title');
      const badgeEl = document.getElementById('status-badge');
      const hoursEl = document.getElementById('today-hours');
      if (titleEl) titleEl.textContent = 'HOY · ' + dateFormatted;
      if (!badgeEl || !hoursEl) return;
      
      const exceptions = (CALENDARIO.places_exceptions && CALENDARIO.places_exceptions[slug]) || {{}};
      const h = d.horario.toLowerCase();
      
      if (h.includes('consultar')) return;
      
      function parseIntervals(text) {{
        const intervals = [];
        const re = /(\d{{1,2}})(?::(\d{{2}}))?\s*[–\-—a]\s*(\d{{1,2}})(?::(\d{{2}}))?h?/gi;
        let m;
        while ((m = re.exec(text)) !== null) {{
          const sh = parseInt(m[1], 10), sm = m[2] ? parseInt(m[2], 10) : 0;
          const eh = parseInt(m[3], 10), em = m[4] ? parseInt(m[4], 10) : 0;
          intervals.push({{
            startMin: sh * 60 + sm,
            endMin: eh * 60 + em,
            startStr: `${{sh}}:${{sm < 10 ? '0' : ''}}${{sm}}`,
            endStr: `${{eh}}:${{em < 10 ? '0' : ''}}${{em}}`
          }});
        }}
        return intervals;
      }}

      // 1. Festivos
      if (CALENDARIO.holidays && CALENDARIO.holidays[dateKey]) {{
        const holidayName = CALENDARIO.holidays[dateKey];
        if (!h.includes('festivos') || h.includes('festivos cerrado') || h.includes('cerrado sáb, dom y festivos')) {{
          badgeEl.className = 'status-badge status-closed';
          badgeEl.textContent = 'Cerrado';
          hoursEl.textContent = `Cerrado por festivo (${{holidayName}})`;
          return;
        }}
      }}

      // 2. Cierre verano
      if (exceptions.summer_closure) {{
        if (monthDay >= exceptions.summer_closure.start && monthDay <= exceptions.summer_closure.end) {{
          badgeEl.className = 'status-badge status-closed';
          badgeEl.textContent = 'Cerrado';
          hoursEl.textContent = 'Cerrado por vacaciones de verano';
          return;
        }}
      }}

      // 3. Universidades agosto
      if (exceptions.august_schedule) {{
        const aug = exceptions.august_schedule;
        if (monthDay >= aug.closure_start && monthDay <= aug.closure_end) {{
          badgeEl.className = 'status-badge status-closed';
          badgeEl.textContent = 'Cerrado';
          hoursEl.textContent = 'Cerrado por periodo estival';
          return;
        }} else if (monthDay >= aug.reduced_start && monthDay <= aug.reduced_end) {{
          if (day >= 1 && day <= 5) {{
            const ivs = parseIntervals(aug.reduced_schedule);
            const open = ivs.some(iv => currentMinutes >= iv.startMin && currentMinutes < iv.endMin);
            badgeEl.className = 'status-badge ' + (open ? 'status-open' : 'status-closed');
            badgeEl.textContent = open ? 'Abierto' : 'Cerrado';
            hoursEl.textContent = aug.reduced_schedule + ' (Horario de agosto)';
            return;
          }} else {{
            badgeEl.className = 'status-badge status-closed';
            badgeEl.textContent = 'Cerrado';
            hoursEl.textContent = 'Cerrado los fines de semana de agosto';
            return;
          }}
        }}
      }}

      // 4. Verano bibliotecas municipales
      if (exceptions.summer_period) {{
        if (monthDay >= exceptions.summer_period.start && monthDay <= exceptions.summer_period.end) {{
          if (day >= 1 && day <= 5) {{
            const ivs = parseIntervals(exceptions.summer_period.weekday_schedule);
            const open = ivs.some(iv => currentMinutes >= iv.startMin && currentMinutes < iv.endMin);
            badgeEl.className = 'status-badge ' + (open ? 'status-open' : 'status-closed');
            badgeEl.textContent = open ? 'Abierto' : 'Cerrado';
            hoursEl.textContent = exceptions.summer_period.weekday_schedule + ' (Horario de verano)';
            return;
          }}
        }}
      }}

      // 5. Normal
      const lines = d.horario.split('\n');
      let target = '';
      if (day === 0) {{
        if (h.includes('dom') || h.includes('fines de semana') || h.includes('lun–dom') || h.includes('lun-dom')) {{
          if (h.includes('sáb–dom') || h.includes('sab-dom')) {{
            const m = d.horario.match(/S[áa]b[–\-—]Dom\s+([^\n·]+)/i);
            if (m) target = m[1];
          }} else if (h.includes('fines de semana')) {{
            const m = d.horario.match(/Fines de semana[^\d]*(\d[^\n·]+)/i);
            if (m) target = m[1];
          }} else if (h.includes('dom') && !h.includes('cerrado')) {{
            const m = d.horario.match(/Dom\s+([^\n·]+)/i);
            if (m) target = m[1];
          }} else if (h.includes('lun–dom') || h.includes('lun-dom')) {{
            target = lines[0];
          }}
        }}
      }} else if (day === 6) {{
        if (h.includes('sáb') || h.includes('sab') || h.includes('fines de semana') || h.includes('lun–dom') || h.includes('lun-dom') || h.includes('lun–sáb') || h.includes('lun-sab')) {{
          if (h.includes('sáb–dom') || h.includes('sab-dom')) {{
            const m = d.horario.match(/S[áa]b[–\-—]Dom\s+([^\n·]+)/i);
            if (m) target = m[1];
          }} else if (h.includes('sáb') || h.includes('sab')) {{
            const m = d.horario.match(/S[áa]b\s+([^\n·\(\)]+)/i);
            if (m) target = m[1];
          }} else if (h.includes('fines de semana')) {{
            const m = d.horario.match(/Fines de semana[^\d]*(\d[^\n·\(\)]+)/i);
            if (m) target = m[1];
          }} else if (h.includes('lun–sáb') || h.includes('lun-sab') || h.includes('lun–dom') || h.includes('lun-dom')) {{
            target = lines[0];
          }}
        }}
      }} else {{
        target = lines[0].split('·')[0];
      }}

      if (!target) {{
        badgeEl.className = 'status-badge status-closed';
        badgeEl.textContent = 'Cerrado';
        hoursEl.textContent = 'Cerrado hoy';
        return;
      }}

      const ivs = parseIntervals(target);
      if (ivs.length > 0) {{
        const open = ivs.some(iv => currentMinutes >= iv.startMin && currentMinutes < iv.endMin);
        badgeEl.className = 'status-badge ' + (open ? 'status-open' : 'status-closed');
        badgeEl.textContent = open ? 'Abierto' : 'Cerrado';
        hoursEl.textContent = ivs.map(iv => iv.startStr + '–' + iv.endStr + 'h').join(' y ');
      }}
    }}
    updateToday();
    setInterval(updateToday, 60000);

    if (d.libcal_lid) {{
      function fTime(t) {{
        if (!t) return '';
        const m = t.trim().match(/^(\\d{1,2})(?::(\\d{{2}}))?\\s*(am|pm)?$/i);
        if (!m) return t;
        let h = parseInt(m[1], 10);
        const min = m[2] || '00';
        if (m[3] && m[3].toLowerCase() === 'pm' && h < 12) h += 12;
        if (m[3] && m[3].toLowerCase() === 'am' && h === 12) h = 0;
        return h + ':' + min;
      }}

      fetch('https://biblioagenda.uam.es/api_hours_today.php?iid=3941&lid=' + d.libcal_lid + '&format=json')
        .then(r => r.json())
        .then(data => {{
          const loc = (data.locations && data.locations.length > 0) ? data.locations[0] : null;
          if (!loc) return;
          const status = loc.times ? loc.times.status : null;
          const isClosed = status === 'closed' || (status === 'text' && /cerrad/i.test(loc.rendered || loc.times.text || '')) || /cerrad/i.test(loc.rendered || '');
          const badgeEl = document.getElementById('status-badge');
          const hoursEl = document.getElementById('today-hours');
          if (!badgeEl || !hoursEl) return;
          if (isClosed) {{
            badgeEl.className = 'status-badge status-closed';
            badgeEl.textContent = 'Cerrado';
            hoursEl.textContent = 'Cerrado hoy';
          }} else if (status === 'open' && loc.times.hours) {{
            const str = loc.times.hours.map(h => fTime(h.from) + '–' + fTime(h.to) + 'h').join(' y ');
            const isOpen = !!loc.times.currently_open;
            badgeEl.className = 'status-badge ' + (isOpen ? 'status-open' : 'status-closed');
            badgeEl.textContent = isOpen ? 'Abierto' : 'Cerrado';
            hoursEl.textContent = str;
          }}
        }})
        .catch(() => {{}});

      fetch('https://biblioagenda.uam.es/api_hours_grid.php?iid=3941&format=json')
        .then(r => r.json())
        .then(data => {{
          const loc = (data.locations || []).find(l => l.lid === d.libcal_lid);
          if (!loc || !loc.weeks || loc.weeks.length === 0) return;
          const week = loc.weeks[0];
          const weekEl = document.getElementById('panel-uam-week');
          if (!weekEl) return;
          const dayLabels = {{ Monday: 'Lun', Tuesday: 'Mar', Wednesday: 'Mié', Thursday: 'Jue', Friday: 'Vie', Saturday: 'Sáb', Sunday: 'Dom' }};
          const now = new Date();
          const todayStr = now.getFullYear() + '-' + String(now.getMonth() + 1).padStart(2, '0') + '-' + String(now.getDate()).padStart(2, '0');
          let rowsHtml = '';
          for (const [dayName, dayInfo] of Object.entries(week)) {{
            const isToday = dayInfo.date === todayStr;
            const label = dayLabels[dayName] || dayName;
            const dayNum = dayInfo.date ? dayInfo.date.slice(8) : '';
            let hoursText = 'Cerrado';
            if (dayInfo.times && dayInfo.times.status === 'open' && dayInfo.times.hours) {{
              hoursText = dayInfo.times.hours.map(h => fTime(h.from) + '–' + fTime(h.to) + 'h').join(' y ');
            }} else if (dayInfo.rendered && !/cerrad/i.test(dayInfo.rendered) && /\\d/.test(dayInfo.rendered)) {{
              hoursText = dayInfo.rendered;
            }}
            rowsHtml += '<tr class="' + (isToday ? 'day-row-today' : '') + '"><td>' + label + ' ' + dayNum + (isToday ? ' (Hoy)' : '') + '</td><td class="day-hours">' + hoursText + '</td></tr>';
          }}
          weekEl.innerHTML = '<div style="font-size:9.5px; font-weight:700; text-transform:uppercase; color:var(--ink-3); margin-top:8px; margin-bottom:4px;">Semana en directo (BiblioAgenda)</div><table class="panel-week-table"><tbody>' + rowsHtml + '</tbody></table>';
        }})
        .catch(() => {{}});
    }}
  }})();
  </script>
</body>
</html>
"""


def sitemap_xml(slugs):
    urls = [f"  <url><loc>{BASE}</loc><lastmod>{LASTMOD}</lastmod><changefreq>monthly</changefreq><priority>1.0</priority></url>"]
    for s in slugs:
        urls.append(
            f"  <url><loc>{BASE}{s}</loc><lastmod>{LASTMOD}</lastmod><changefreq>monthly</changefreq><priority>0.7</priority></url>"
        )
    return '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "\n".join(urls) + "\n</urlset>\n"


def main():
    root = os.path.dirname(os.path.abspath(__file__))
    index_path = os.path.join(root, "index.html")

    print(f"Leyendo {index_path}...")
    lugares = extract_lugares(index_path)
    slugs = unique_slugs(lugares)

    # 1. Generar HTML por centro
    for d, s in zip(lugares, slugs):
        out_path = os.path.join(root, f"{s}.html")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(page_html(d, s))

    # 2. Generar sitemap.xml
    sitemap_path = os.path.join(root, "sitemap.xml")
    with open(sitemap_path, "w", encoding="utf-8") as f:
        f.write(sitemap_xml(slugs))

    print(f"Generadas {len(lugares)} páginas + sitemap.xml ({len(slugs) + 1} URLs).")
    for s, d in list(zip(slugs, lugares))[:6]:
        print(f"  {s:42s} <- {d['nombre']}")


if __name__ == "__main__":
    main()
