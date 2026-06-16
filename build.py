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
LASTMOD = "2026-06-16"

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


def page_html(d, slug):
    c = COLORES[d["tipo"]]
    e = html.escape
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

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
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
    .addr {{ font-size:13.5px; color:var(--ink-3); margin-bottom:20px; line-height:1.5; }}
    .sched h2 {{ font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:0.07em; color:var(--ink-3); margin-bottom:6px; }}
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
    <div class="sched"><h2>Horario</h2>{horario_html}</div>
    <div class="actions">
      <a class="btn btn-primary" href="./#{slug}">Ver en el mapa</a>
      <a class="btn btn-ghost" href="{e(web)}" target="_blank" rel="noopener noreferrer">{e(web_label)} ↗</a>
    </div>
    <footer>
      Datos: <a href="https://datos.madrid.es" target="_blank" rel="noopener">datos.madrid.es</a> (CC BY 4.0).
      Horarios orientativos; confirma siempre en la web del centro.
    </footer>
  </main>
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
