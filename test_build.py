import copy
import os
import unittest

import build


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
        self.assertEqual(sitemap.count("<url>"), len(self.slugs) + 3)


if __name__ == "__main__":
    unittest.main()
