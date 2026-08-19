#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Genera una página HTML por cada lugar (SEO) + sitemap.xml a partir del array
`lugares` que vive dentro de index.html (fuente única de datos).

El algoritmo de "slug" debe ser IDÉNTICO al de index.html (función slugify en JS),
para que las URLs de las páginas coincidan con las que enlaza el panel del mapa.

Uso:  python build.py
"""
import re, json, unicodedata, html, os, sys

BASE = "https://bibliotecasmadrid.github.io/Donde-estudio-hoy/"
ROOT = os.path.dirname(os.path.abspath(__file__))
LASTMOD = "2026-08-19"

COLORES = {
    "biblioteca":  {"fill": "#2563EB", "label": "Biblioteca pública"},
    "sala":        {"fill": "#059669", "label": "Sala de estudio"},
    "universidad": {"fill": "#7C3AED", "label": "Universidad / BNE"},
}

# Prefijos genéricos que se quitan del nombre para acortar el slug (primer match).
PREFIJOS = [
    "biblioteca pública ", "biblioteca municipal ", "salas de estudio ",
    "sala de estudio del ", "sala de estudio de la ", "sala de estudio ",
    "sala de lectura ", "biblioteca ",
]


def strip_accents(s):
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def slugify(nombre):
    base = nombre
    low = nombre.lower()
    for p in PREFIJOS:
        if low.startswith(p):
            base = nombre[len(p):]
            break
    base = strip_accents(base).lower()
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
    # quitar líneas que sean solo comentario
    body = "\n".join(ln for ln in body.split("\n") if not ln.strip().startswith("//"))
    # poner comillas a las claves (case-sensitive, deben ir seguidas de ':')
    body = re.sub(r'(?<![\w"])(tipo|nombre|distrito|direccion|lat|lng|horario|web)\s*:',
                  r'"\1":', body)
    jtext = "[" + body + "]"
    jtext = re.sub(r",(\s*[}\]])", r"\1", jtext)  # comas colgantes
    return json.loads(jtext)


def web_url(d):
    if d.get("web"):
        return d["web"], "Web oficial"
    from urllib.parse import quote_plus
    return "https://www.google.com/search?q=" + quote_plus(d["nombre"] + " Madrid"), "Buscar web y horario"


def get_today_info(horario_str, now=None):
    if now is None:
        import datetime
        now = datetime.datetime.now()
    day = (now.weekday() + 1) % 7  # 0: Dom, 1: Lun, ..., 6: Sab
    month = now.month  # 1-12
    day_of_month = now.day
    current_minutes = now.hour * 60 + now.minute
    
    is_summer = (month in (7, 8) or (month == 6 and day_of_month >= 15) or (month == 9 and day_of_month <= 15))
    is_july_august = (month in (7, 8))
    
    h = horario_str.lower()
    
    if 'consultar' in h or 'teléfono' in h or 'telefono' in h:
        return {
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

    lines = horario_str.split('\n')
    main_line = lines[0]
    
    # Domingo (0)
    if day == 0:
        if any(k in h for k in ['dom', 'fines de semana', 'lun–dom', 'lun-dom']):
            sunday_text = ''
            if 'sáb–dom' in h or 'sab-dom' in h or 'sáb y dom' in h:
                m = re.search(r'S[áa]b[–\-—]Dom\s+([^\n·]+)', horario_str, re.IGNORECASE)
                if m: sunday_text = m.group(1)
            elif 'fines de semana' in h:
                m = re.search(r'Fines de semana[^\d]*(\d[^\n·]+)', horario_str, re.IGNORECASE)
                if m: sunday_text = m.group(1)
            elif 'dom' in h and 'cerrado' not in h:
                m = re.search(r'Dom\s+([^\n·]+)', horario_str, re.IGNORECASE)
                if m: sunday_text = m.group(1)
            elif 'lun–dom' in h or 'lun-dom' in h:
                sunday_text = main_line
                
            if sunday_text:
                intervals = parse_intervals(sunday_text)
                if intervals:
                    is_open = any(iv['start_min'] <= current_minutes < iv['end_min'] for iv in intervals)
                    sched_formatted = ' y '.join(f"{iv['start_str']}–{iv['end_str']}h" for iv in intervals)
                    return {
                        'status_text': 'Abierto' if is_open else 'Cerrado',
                        'status_class': 'status-open' if is_open else 'status-closed',
                        'today_schedule': sched_formatted,
                        'is_open': is_open
                    }
        return {
            'status_text': 'Cerrado',
            'status_class': 'status-closed',
            'today_schedule': 'Cerrado hoy',
            'is_open': False
        }
        
    # Sábado (6)
    if day == 6:
        if any(k in h for k in ['sáb', 'sab', 'fines de semana', 'lun–dom', 'lun-dom', 'lun–sáb', 'lun-sab']):
            sab_text = ''
            if 'sáb–dom' in h or 'sab-dom' in h or 'sáb y dom' in h:
                m = re.search(r'S[áa]b[–\-—]Dom\s+([^\n·]+)', horario_str, re.IGNORECASE)
                if m: sab_text = m.group(1)
            elif 'sáb' in h or 'sab' in h:
                m = re.search(r'S[áa]b\s+([^\n·\(\)]+)', horario_str, re.IGNORECASE)
                if m: sab_text = m.group(1)
            elif 'fines de semana' in h:
                m = re.search(r'Fines de semana[^\d]*(\d[^\n·\(\)]+)', horario_str, re.IGNORECASE)
                if m: sab_text = m.group(1)
            elif any(k in h for k in ['lun–sáb', 'lun-sab', 'lun–dom', 'lun-dom']):
                sab_text = main_line
                
            if sab_text:
                intervals = parse_intervals(sab_text)
                if intervals:
                    is_open = any(iv['start_min'] <= current_minutes < iv['end_min'] for iv in intervals)
                    sched_formatted = ' y '.join(f"{iv['start_str']}–{iv['end_str']}h" for iv in intervals)
                    return {
                        'status_text': 'Abierto' if is_open else 'Cerrado',
                        'status_class': 'status-open' if is_open else 'status-closed',
                        'today_schedule': sched_formatted,
                        'is_open': is_open
                    }
        return {
            'status_text': 'Cerrado',
            'status_class': 'status-closed',
            'today_schedule': 'Cerrado hoy',
            'is_open': False
        }
        
    # Lunes a Viernes (1-5)
    if day == 5 and 'vie 9–14:30h' in h:
        intervals = parse_intervals('9–14:30h')
        is_open = any(iv['start_min'] <= current_minutes < iv['end_min'] for iv in intervals)
        return {
            'status_text': 'Abierto' if is_open else 'Cerrado',
            'status_class': 'status-open' if is_open else 'status-closed',
            'today_schedule': '9:00–14:30h',
            'is_open': is_open
        }
        
    line_to_use = main_line
    if is_summer:
        summer_line = next((l for l in lines if 'verano' in l.lower() or (is_july_august and ('julio' in l.lower() or 'agosto' in l.lower()))), None)
        if summer_line:
            line_to_use = summer_line
            
    weekday_part = line_to_use.split('·')[0] if '·' in line_to_use else line_to_use
    intervals = parse_intervals(weekday_part)
    if intervals:
        is_open = any(iv['start_min'] <= current_minutes < iv['end_min'] for iv in intervals)
        sched_formatted = ' y '.join(f"{iv['start_str']}–{iv['end_str']}h" for iv in intervals)
        return {
            'status_text': 'Abierto' if is_open else 'Cerrado',
            'status_class': 'status-open' if is_open else 'status-closed',
            'today_schedule': sched_formatted,
            'is_open': is_open
        }
        
    return {
        'status_text': 'Abierto',
        'status_class': 'status-open',
        'today_schedule': main_line,
        'is_open': True
    }


def page_html(d, slug):
    c = COLORES[d["tipo"]]
    e = html.escape
    today = get_today_info(d["horario"])
    horario_inline = d["horario"].replace("\n", " ")
    horario_html = "".join(f"<div>{e(l)}</div>" for l in d["horario"].split("\n"))
    web, web_label = web_url(d)
    desc = f'{d["nombre"]}: {d["direccion"]}. Horario: {horario_inline}. {c["label"]} en Madrid.'
    canonical = BASE + slug

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
        "geo": {"@type": "GeoCoordinates", "latitude": d["lat"], "longitude": d["lng"]},
        "url": canonical,
        "areaServed": "Madrid",
    }

    horario_json = json.dumps(d["horario"], ensure_ascii=False)

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
  <script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>
  <style>
    :root {{ --ink:#1A1F36; --ink-2:#5A6172; --ink-3:#9AA0AE; --line:#ECEEF2; }}
    * {{ margin:0; padding:0; box-sizing:border-box; }}
    body {{
      font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;
      -webkit-font-smoothing:antialiased; background:#EAEDF0; color:var(--ink);
      min-height:100vh; display:flex; align-items:center; justify-content:center; padding:24px;
    }}
    .card {{
      background:#fff; max-width:460px; width:100%; border-radius:20px; padding:28px 28px 24px;
      box-shadow:0 12px 40px rgba(20,30,60,0.14);
    }}
    .back {{ display:inline-block; font-size:13px; color:var(--ink-2); text-decoration:none; margin-bottom:16px; }}
    .back:hover {{ color:var(--ink); }}
    .badge {{
      display:inline-block; font-size:10px; font-weight:700; letter-spacing:0.06em; text-transform:uppercase;
      padding:3px 10px; border-radius:999px; color:#fff; margin-bottom:12px; background:{c["fill"]};
    }}
    h1 {{ font-size:23px; font-weight:800; letter-spacing:-0.01em; line-height:1.25; margin-bottom:8px; }}
    .addr {{ font-size:13.5px; color:var(--ink-3); margin-bottom:16px; line-height:1.5; }}
    
    /* ── Box HOY ───────────────────────────── */
    .today-card {{
      background: #F8FAFC;
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 12px 15px;
      margin-bottom: 16px;
    }}
    .today-head {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 5px;
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
      font-size: 14px;
      font-weight: 700;
      color: var(--ink);
    }}

    .sched h2 {{ font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.07em; color: var(--ink-3); margin-bottom: 6px; }}
    .sched {{ font-size:14.5px; line-height:1.7; border-top:1px solid var(--line); padding-top:16px; }}
    .actions {{ display:flex; flex-wrap:wrap; gap:10px; margin-top:22px; }}
    .btn {{
      display:inline-flex; align-items:center; gap:6px; font-size:13.5px; font-weight:600;
      text-decoration:none; padding:9px 16px; border-radius:999px; transition:filter .12s ease;
    }}
    .btn-primary {{ background:{c["fill"]}; color:#fff; }}
    .btn-primary:hover {{ filter:brightness(1.08); }}
    .btn-ghost {{ background:#F1F3F7; color:var(--ink); }}
    .btn-ghost:hover {{ background:#E7EAF0; }}
    footer {{ margin-top:22px; font-size:11px; color:var(--ink-3); line-height:1.5; }}
    footer a {{ color:var(--ink-3); }}
  </style>
</head>
<body>
  <main class="card">
    <a class="back" href="./">← Mapa de bibliotecas y salas de estudio de Madrid</a>
    <span class="badge">{e(c["label"])}</span>
    <h1>{e(d["nombre"])}</h1>
    <p class="addr">{e(d["distrito"])} · {e(d["direccion"])}</p>
    
    <div class="today-card" id="today-card">
      <div class="today-head">
        <span class="today-title">HOY</span>
        <span class="status-badge {today['status_class']}" id="status-badge">{today['status_text']}</span>
      </div>
      <div class="today-hours" id="today-hours">{today['today_schedule']}</div>
    </div>

    <div class="sched"><h2>Horario habitual</h2>{horario_html}</div>
    <div class="actions">
      <a class="btn btn-primary" href="./#{slug}">Ver en el mapa</a>
      <a class="btn btn-ghost" href="{e(web)}" target="_blank" rel="noopener noreferrer">{e(web_label)} ↗</a>
    </div>
    <footer>
      Datos: <a href="https://datos.madrid.es" target="_blank" rel="noopener">datos.madrid.es</a> (CC BY 4.0).
      Horarios orientativos; confirma siempre en la web del centro.
    </footer>
  </main>

  <script>
  (function() {{
    const horarioStr = {horario_json};
    function updateToday() {{
      const d = new Date();
      const day = d.getDay();
      const month = d.getMonth();
      const dayOfMonth = d.getDate();
      const mins = d.getHours() * 60 + d.getMinutes();
      const isSummer = (month === 6 || month === 7 || (month === 5 && dayOfMonth >= 15) || (month === 8 && dayOfMonth <= 15));
      const isJulyAugust = (month === 6 || month === 7);
      const h = horarioStr.toLowerCase();
      
      if (h.includes('consultar') || h.includes('teléfono') || h.includes('telefono')) return;

      function parse(text) {{
        const ivs = [];
        const re = /(\\d{{1,2}})(?::(\\d{{2}}))?\\s*[–\\-—a]\\s*(\\d{{1,2}})(?::(\\d{{2}}))?h?/gi;
        let m;
        while ((m = re.exec(text)) !== null) {{
          const sh = parseInt(m[1], 10), sm = m[2] ? parseInt(m[2], 10) : 0;
          const eh = parseInt(m[3], 10), em = m[4] ? parseInt(m[4], 10) : 0;
          ivs.push({{ s: sh * 60 + sm, e: eh * 60 + em, sStr: sh + ':' + (sm < 10 ? '0' : '') + sm, eStr: eh + ':' + (em < 10 ? '0' : '') + em }});
        }}
        return ivs;
      }}

      const lines = horarioStr.split('\\n');
      let target = '';
      if (day === 0) {{
        if (h.includes('dom') || h.includes('fines de semana') || h.includes('lun–dom') || h.includes('lun-dom')) {{
          if (h.includes('sáb–dom') || h.includes('sab-dom')) {{
            const m = horarioStr.match(/S[áa]b[–\\-—]Dom\\s+([^\\n·]+)/i);
            if (m) target = m[1];
          }} else if (h.includes('fines de semana')) {{
            const m = horarioStr.match(/Fines de semana[^\\d]*(\\d[^\\n·]+)/i);
            if (m) target = m[1];
          }} else if (h.includes('dom') && !h.includes('cerrado')) {{
            const m = horarioStr.match(/Dom\\s+([^\\n·]+)/i);
            if (m) target = m[1];
          }} else if (h.includes('lun–dom') || h.includes('lun-dom')) {{
            target = lines[0];
          }}
        }}
      }} else if (day === 6) {{
        if (h.includes('sáb') || h.includes('sab') || h.includes('fines de semana') || h.includes('lun–dom') || h.includes('lun-dom') || h.includes('lun–sáb') || h.includes('lun-sab')) {{
          if (h.includes('sáb–dom') || h.includes('sab-dom')) {{
            const m = horarioStr.match(/S[áa]b[–\\-—]Dom\\s+([^\\n·]+)/i);
            if (m) target = m[1];
          }} else if (h.includes('sáb') || h.includes('sab')) {{
            const m = horarioStr.match(/S[áa]b\\s+([^\\n·\\(\\)]+)/i);
            if (m) target = m[1];
          }} else if (h.includes('fines de semana')) {{
            const m = horarioStr.match(/Fines de semana[^\\d]*(\\d[^\\n·\\(\\)]+)/i);
            if (m) target = m[1];
          }} else if (h.includes('lun–sáb') || h.includes('lun-sab') || h.includes('lun–dom') || h.includes('lun-dom')) {{
            target = lines[0];
          }}
        }}
      }} else {{
        if (day === 5 && h.includes('vie 9–14:30h')) {{
          target = '9–14:30h';
        }} else {{
          target = lines[0];
          if (isSummer) {{
            const sLine = lines.find(l => l.toLowerCase().includes('verano') || (isJulyAugust && (l.toLowerCase().includes('julio') || l.toLowerCase().includes('agosto'))));
            if (sLine) target = sLine;
          }}
          if (target.includes('·')) target = target.split('·')[0];
        }}
      }}

      const badge = document.getElementById('status-badge');
      const hours = document.getElementById('today-hours');
      if (!badge || !hours) return;

      if (!target) {{
        badge.className = 'status-badge status-closed';
        badge.textContent = 'Cerrado';
        hours.textContent = 'Cerrado hoy';
        return;
      }}

      const ivs = parse(target);
      if (ivs.length > 0) {{
        const open = ivs.some(iv => mins >= iv.s && mins < iv.e);
        badge.className = 'status-badge ' + (open ? 'status-open' : 'status-closed');
        badge.textContent = open ? 'Abierto' : 'Cerrado';
        hours.textContent = ivs.map(iv => iv.sStr + '–' + iv.eStr + 'h').join(' y ');
      }}
    }}
    updateToday();
  }})();
  </script>
</body>
</html>
"""


def main():
    index_path = os.path.join(ROOT, "index.html")
    lugares = extract_lugares(index_path)
    slugs = unique_slugs(lugares)

    n = 0
    for d, slug in zip(lugares, slugs):
        with open(os.path.join(ROOT, slug + ".html"), "w", encoding="utf-8") as f:
            f.write(page_html(d, slug))
        n += 1

    # sitemap
    urls = [(BASE, "1.0")] + [(BASE + s, "0.7") for s in slugs]
    parts = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for loc, prio in urls:
        parts.append(f"  <url><loc>{loc}</loc><lastmod>{LASTMOD}</lastmod>"
                     f"<changefreq>monthly</changefreq><priority>{prio}</priority></url>")
    parts.append("</urlset>\n")
    with open(os.path.join(ROOT, "sitemap.xml"), "w", encoding="utf-8") as f:
        f.write("\n".join(parts))

    print(f"Generadas {n} páginas + sitemap.xml ({len(urls)} URLs).")
    # muestra algunos slugs para revisar
    for d, s in list(zip(lugares, slugs))[:6]:
        print(f"  {s:42s} <- {d['nombre']}")


if __name__ == "__main__":
    main()
