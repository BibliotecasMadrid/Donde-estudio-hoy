#!/usr/bin/env python3
"""
sync_uam.py - Sincroniza los horarios de la UAM desde LibCal (BiblioAgenda).
Descarga los horarios de https://biblioagenda.uam.es/api_hours_grid.php?iid=3941&format=json
y actualiza las excepciones de calendario.json para todas las bibliotecas de la UAM.
"""

import json
import os
import urllib.request

IID = 3941
API_TODAY = f"https://biblioagenda.uam.es/api_hours_today.php?iid={IID}&lid=0&format=json"
API_GRID = f"https://biblioagenda.uam.es/api_hours_grid.php?iid={IID}&format=json"

# Mapeo de lid de LibCal a slugs de nuestro proyecto
LIBCAL_TO_SLUG = {
    5663: "uam-ciencias-fernando-gonzalez-bernaldez",
    5672: "uam-facultad-de-derecho-cantoblanco",
    5665: "uam-ciencias-economicas-cantoblanco",
    5589: "uam-facultad-de-educacion-cantoblanco",
    5673: "uam-humanidades-cantoblanco",
    5674: "uam-facultad-de-medicina",
    5676: "uam-facultad-de-psicologia-cantoblanco",
    5675: "uam-escuela-politecnica-superior",
    5671: "uam-sala-buho"
}

def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "DondeEstudioHoy/1.0 (Mozilla/5.0)"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))

def sync_uam():
    print(f"Descargando datos en vivo de BiblioAgenda UAM ({API_GRID})...")
    grid_data = fetch_json(API_GRID)
    locations = grid_data.get("locations", [])
    print(f"Recibidas {len(locations)} ubicaciones de la UAM.")

    root_dir = os.path.dirname(os.path.abspath(__file__))
    cal_path = os.path.join(root_dir, "calendario.json")

    with open(cal_path, "r", encoding="utf-8") as f:
        cal = json.load(f)

    if "places_exceptions" not in cal:
        cal["places_exceptions"] = {}

    updated_count = 0
    for loc in locations:
        lid = loc.get("lid")
        slug = LIBCAL_TO_SLUG.get(lid)
        if not slug:
            continue

        weeks = loc.get("weeks", [])
        if not weeks:
            continue

        print(f"Procesando {loc.get('name')} (LID: {lid} -> slug: {slug})...")

        closure_days = []
        reduced_days = []
        reduced_hours = None

        for week in weeks:
            for day_name, day_info in week.items():
                date_str = day_info.get("date")
                if not date_str:
                    continue
                month_day = date_str[5:]
                times = day_info.get("times", {})
                status = times.get("status")
                rendered = day_info.get("rendered", "")

                if status == "text" and "cerrad" in rendered.lower():
                    closure_days.append(month_day)
                elif status == "open":
                    hrs = times.get("hours", [])
                    if hrs:
                        f_h, t_h = hrs[0].get("from", ""), hrs[0].get("to", "")
                        h_str = f"{f_h} - {t_h}"
                        if "2pm" in h_str or "14:00" in h_str:
                            reduced_days.append(month_day)
                            reduced_hours = "9:00–14:00h"

        if slug not in cal["places_exceptions"]:
            cal["places_exceptions"][slug] = {}

        existing_exam = cal["places_exceptions"][slug].get("exam_periods", [
            {"start": "01-08", "end": "02-15", "schedule": "24h / Horario ampliado"},
            {"start": "05-10", "end": "06-30", "schedule": "24h / Horario ampliado"}
        ])
        cal["places_exceptions"][slug]["exam_periods"] = existing_exam

        august_closures = [d for d in closure_days if d.startswith("08-")]
        august_reduced = [d for d in reduced_days if d.startswith("08-")]

        if august_closures:
            aug_start = min(august_closures)
            aug_end = max(august_closures)
            aug_dict = {
                "closure_start": aug_start,
                "closure_end": aug_end
            }
            if august_reduced:
                aug_dict["reduced_start"] = min(august_reduced)
                aug_dict["reduced_end"] = max(august_reduced)
                aug_dict["reduced_schedule"] = reduced_hours or "9:00–14:00h"
            else:
                aug_dict["reduced_start"] = "08-24"
                aug_dict["reduced_end"] = "08-31"
                aug_dict["reduced_schedule"] = "9:00–14:00h"

            cal["places_exceptions"][slug]["august_schedule"] = aug_dict
            updated_count += 1

    cal["last_updated"] = "2026-08-19"

    with open(cal_path, "w", encoding="utf-8") as f:
        json.dump(cal, f, indent=2, ensure_ascii=False)

    print(f"\nSincronización completada. {updated_count} bibliotecas UAM actualizadas en calendario.json.")

if __name__ == "__main__":
    sync_uam()
