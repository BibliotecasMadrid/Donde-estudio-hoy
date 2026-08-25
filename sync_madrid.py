#!/usr/bin/env python3
"""
sync_madrid.py - Sincroniza los horarios de salas de estudio desde madrid.es.

Este script:
1. Extrae las URLs de madrid.es de index.html.
2. Descarga cada página (requiere IP sin bloqueo de Akamai, ej. conexión doméstica).
3. Extrae el bloque de "Horario".
4. Actualiza index.html para que el text fragment (#:~:text=...) abarque todo el bloque.
5. Avisa si detecta horario de verano para poder añadirlo a calendario.json.

Uso:
  pip install requests beautifulsoup4
  python sync_madrid.py
"""

import re
import requests
from bs4 import BeautifulSoup

def main():
    print("Iniciando sincronización con madrid.es...")
    
    with open("index.html", "r", encoding="utf-8") as f:
        html_content = f.read()
        
    pattern = r'\{[^}]*web:\s*"(https://www\.madrid\.es/sites/[^"]+)"[^}]*\}'
    matches = re.finditer(pattern, html_content)
    lugares_actualizados = 0
    
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "es-ES,es;q=0.9"
    })
    
    for match in matches:
        lugar_str = match.group(0)
        url_full = match.group(1)
        url_base = url_full.split('#:~:text=')[0]
        
        nombre_match = re.search(r'nombre:\s*"([^"]+)"', lugar_str)
        nombre = nombre_match.group(1) if nombre_match else "Desconocido"
        
        print(f"\nConsultando: {nombre}")
        try:
            res = session.get(url_base, timeout=10)
            res.raise_for_status()
        except Exception as e:
            print(f"  Error al acceder: {e}")
            continue
            
        soup = BeautifulSoup(res.text, "html.parser")
        
        horario_text = ""
        for tag in soup.find_all(['h2', 'h3', 'h4', 'strong', 'span']):
            if tag.get_text() and "Horario" in tag.get_text():
                parent = tag.parent
                if parent.name in ['div', 'li']:
                    horario_text = parent.get_text(separator=" ", strip=True)
                else:
                    sibling = tag.find_next_sibling(['p', 'ul', 'div'])
                    if sibling:
                        horario_text = sibling.get_text(separator=" ", strip=True)
                break
                
        if not horario_text:
            print("  No se encontró el bloque de horario.")
            continue
            
        words = horario_text.split()
        if len(words) > 5:
            start_text = " ".join(words[:4]).replace(",", "")
            end_text = " ".join(words[-4:]).replace(",", "")
            new_fragment = f"#:~:text={requests.utils.quote(start_text)},{requests.utils.quote(end_text)}"
            new_url = f"{url_base}{new_fragment}"
            
            html_content = html_content.replace(url_full, new_url)
            print(f"  URL fragment actualizado.")
            lugares_actualizados += 1
            
        if "agosto" in horario_text.lower() or "verano" in horario_text.lower():
            print(f"  [!] TIENE HORARIO DE VERANO. Se debe añadir a calendario.json si no está.")
            
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html_content)
        
    print(f"\nSincronización completada. {lugares_actualizados} lugares actualizados.")

if __name__ == "__main__":
    main()
