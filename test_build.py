import copy
import json
import os
import re
import tempfile
import unittest
from collections import Counter
from pathlib import Path

import build
import fotos
from PIL import Image


class BuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lugares = build.extract_lugares(os.path.join(build.ROOT, "index.html"))
        cls.slugs = build.unique_slugs(cls.lugares)
        cls.calendario = build.cargar_calendario()

    def test_verified_full_day_rules_have_sources(self):
        verified = {}
        for slug, profile in self.calendario["places"].items():
            periods = build.fechas_24_horas(profile)
            if periods:
                verified[slug] = periods
                for period in periods:
                    self.assertTrue(period["source"]["url"].startswith("https://"))
                    self.assertRegex(period["source"]["checked_at"], r"^\d{4}-\d{2}-\d{2}$")
        self.assertEqual(
            set(verified),
            {"rafael-alberti", "elena-fortun", "uah-edificio-crai-alcala-centro"},
        )
        self.assertEqual(sum(map(len, verified.values())), 5)

    def test_unverified_full_day_rule_is_rejected(self):
        profile = copy.deepcopy(self.calendario["places"]["rafael-alberti"])
        profile["rules"].append({
            "from": "2026-09-01", "to": "2026-09-02", "estado": "abierto",
            "intervalos": [["00:00", "24:00"]], "priority": 100,
        })
        errors = build.validar_perfil("rafael-alberti", profile, 2026)
        self.assertTrue(any("fuente HTTPS" in error for error in errors), errors)

    def test_landing_pages_are_static_and_canonical(self):
        weekend = build.landing_page_html(self.lugares, self.slugs, self.calendario, "weekend")
        full_day = build.landing_page_html(self.lugares, self.slugs, self.calendario, "full-day")
        self.assertIn(f'<link rel="canonical" href="{build.BASE}{build.WEEKEND_ROUTE}">', weekend)
        self.assertIn(f'<link rel="canonical" href="{build.BASE}{build.FULL_DAY_ROUTE}">', full_day)
        self.assertIn('class="place-card"', weekend)
        self.assertIn('class="place-card"', full_day)
        self.assertIn('type="application/ld+json"', weekend)
        self.assertIn('Fuente oficial', full_day)

    def test_sitemap_includes_only_the_two_topic_routes_once(self):
        sitemap = build.sitemap_xml(self.slugs, self.calendario)
        self.assertEqual(sitemap.count(build.BASE + build.WEEKEND_ROUTE), 1)
        self.assertEqual(sitemap.count(build.BASE + build.FULL_DAY_ROUTE), 1)
        self.assertEqual(sitemap.count(build.BASE + build.DIRECTORY_ROUTE), 1)
        self.assertEqual(sitemap.count("<url>"), len(self.slugs) + 4)

    def test_place_titles_lead_with_the_schedule_prefix(self):
        for lugar, slug in list(zip(self.lugares, self.slugs))[:20]:
            page = build.page_html(lugar, slug)
            expected = f'<title>{build.TITLE_PREFIX} · {lugar["nombre"]}</title>'
            self.assertIn(expected, page)
            self.assertIn(
                f'<meta property="og:title" content="{build.TITLE_PREFIX} · {lugar["nombre"]}">',
                page,
            )

    def test_directory_links_every_place_in_static_html(self):
        page = build.directorio_page_html(self.lugares, self.slugs)
        # El valor de la página es que los enlaces estén en el HTML servido, no que los
        # ponga JavaScript: se comprueba sobre el documento con los <script> quitados.
        sin_script = re.sub(r"<script.*?</script>", "", page, flags=re.S)
        enlaces = set(re.findall(r'href="/([a-z0-9-]+)"', sin_script))
        self.assertTrue(set(self.slugs) <= enlaces, set(self.slugs) - enlaces)
        self.assertIn(f'<link rel="canonical" href="{build.BASE}{build.DIRECTORY_ROUTE}">', page)

    def test_home_links_to_the_directory(self):
        with open(os.path.join(build.ROOT, "index.html"), encoding="utf-8") as source:
            home = source.read()
        self.assertIn(f'href="/{build.DIRECTORY_ROUTE}"', home)

    def test_places_link_back_to_the_directory(self):
        page = build.page_html(self.lugares[0], self.slugs[0])
        self.assertIn(f'href="/{build.DIRECTORY_ROUTE}"', page)

    def test_search_area_catalog_is_complete_and_valid(self):
        path = os.path.join(build.ROOT, "zonas-madrid.geojson")
        with open(path, encoding="utf-8") as source:
            collection = json.load(source)
        self.assertEqual(collection["type"], "FeatureCollection")
        counts = Counter(feature["properties"]["tipo"] for feature in collection["features"])
        self.assertEqual(counts, {"barrio": 131, "distrito": 21, "municipio": 179})
        self.assertEqual(len(collection["features"]), 331)
        for feature in collection["features"]:
            self.assertTrue(feature["properties"]["nombre"].strip())
            self.assertIn(feature["geometry"]["type"], {"Polygon", "MultiPolygon"})

    def test_popular_area_aliases_are_in_the_catalog(self):
        path = os.path.join(build.ROOT, "zonas-madrid.geojson")
        with open(path, encoding="utf-8") as source:
            collection = json.load(source)
        aliases = {
            alias
            for feature in collection["features"]
            for alias in feature["properties"].get("aliases", [])
        }
        self.assertTrue({"Malasaña", "Chueca", "Lavapiés", "Valdebebas"} <= aliases)

    def test_photo_field_can_be_inserted_without_existing_photo(self):
        line = '  { tipo: "biblioteca", nombre: "Centro nuevo", distrito: "Madrid" },'
        result = fotos.fijar_campo(line, "foto_interior", "images/centro-interior.jpg")
        self.assertIn('foto_interior: "images/centro-interior.jpg"', result)
        self.assertTrue(result.endswith(" },"), result)

    def test_photo_field_replacement_preserves_other_visual_fields(self):
        line = ('  { tipo: "biblioteca", nombre: "Centro", '
                'foto: "images/vieja.jpg", foto_credito: "Autora", distrito: "Madrid" },')
        result = fotos.fijar_campo(line, "foto", "images/nueva.jpg")
        self.assertEqual(result.count("foto:"), 1)
        self.assertIn('foto: "images/nueva.jpg"', result)
        self.assertIn('foto_credito: "Autora"', result)

    def test_photo_choices_reject_same_image_for_both_uses(self):
        with tempfile.TemporaryDirectory() as temporal:
            cache = Path(temporal)
            destino = cache / "centro"
            destino.mkdir()
            Image.new("RGB", (20, 20)).save(destino / "01.jpg", "JPEG")
            (destino / "meta.json").write_text(json.dumps({
                "fotos": [{"n": 1, "archivo": "01.jpg", "autor": "Autora"}],
            }), encoding="utf-8")
            with self.assertRaisesRegex(SystemExit, "fotos distintas"):
                fotos.preparar_elecciones(
                    {"centro": {"interior": 1, "exterior": 1}},
                    {"centro": {"nombre": "Centro"}},
                    ['{ nombre: "Centro" },'],
                    cache,
                )

    def test_photo_choices_require_attribution(self):
        with tempfile.TemporaryDirectory() as temporal:
            cache = Path(temporal)
            destino = cache / "centro"
            destino.mkdir()
            Image.new("RGB", (20, 20)).save(destino / "01.jpg", "JPEG")
            (destino / "meta.json").write_text(json.dumps({
                "fotos": [{"n": 1, "archivo": "01.jpg", "autor": ""}],
            }), encoding="utf-8")
            with self.assertRaisesRegex(SystemExit, "no trae atribucion"):
                fotos.preparar_elecciones(
                    {"centro": {"interior": 1}},
                    {"centro": {"nombre": "Centro"}},
                    ['{ nombre: "Centro" },'],
                    cache,
                )


if __name__ == "__main__":
    unittest.main()
