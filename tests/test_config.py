"""Settings files."""
import os
import tempfile
import unittest

from civ6_planner import config, dataset, model
from civ6_planner.rules import Rules
from helpers import full_map, yields


class ConfigTest(unittest.TestCase):
    def write(self, text):
        f = tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False)
        f.write(text)
        f.close()
        self.addCleanup(os.remove, f.name)
        return f.name

    def test_override_only_changes_what_it_sets(self):
        cfg = config.load(self.write("[objective.weights]\nscience = 3.0\n[solver]\ntime_limit = 5.0\n"))
        self.assertEqual(cfg.weights["YIELD_SCIENCE"], 3.0)
        self.assertEqual(cfg.weights["YIELD_FOOD"], config.default().weights["YIELD_FOOD"])
        self.assertEqual(cfg.solver["time_limit"], 5.0)
        self.assertEqual(cfg.city_bonus, config.default().city_bonus)

    def test_empty_file_gives_the_defaults(self):
        cfg = config.load(self.write(""))
        self.assertEqual(cfg.raw, config.default().raw)

    def test_written_settings_load_back_the_same(self):
        cfg = config.load(self.write("[problem]\ndistricts = [\"DISTRICT_CAMPUS\", \"DISTRICT_HOLY_SITE\"]\n"
                                     "[solver]\npresolve = false\n"))
        self.assertEqual(config.load(self.write(config.to_toml(cfg))).raw, cfg.raw)

    def test_case_config_then_command_line_config(self):
        # data/<case>/config.toml overlays the defaults; --config overlays both.
        folder = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, folder)
        with open(os.path.join(folder, "map.json"), "w") as f:
            f.write("{}")
        with open(os.path.join(folder, "config.toml"), "w") as f:
            f.write("[objective.weights]\nscience = 2.0\nfood = 3.0\n")
        self.assertEqual(dataset.config_path(folder), os.path.join(folder, "config.toml"))
        cfg = config.load(dataset.config_path(folder), self.write("[objective.weights]\nscience = 5.0\n"))
        self.assertEqual((cfg.weights["YIELD_SCIENCE"], cfg.weights["YIELD_FOOD"]), (5.0, 3.0))

    def test_case_template_is_empty_settings(self):
        self.assertEqual(config.load(self.write(dataset.CONFIG_TEMPLATE)).raw, config.default().raw)

    def test_unknown_setting_is_an_error(self):
        with self.assertRaises(KeyError):
            config.load(self.write("[objective]\nsite_radios = 3\n"))

    def test_weights_change_the_plan_score(self):
        # Every tile gives 1 food; with food weighted 4 (default 2) the site value doubles.
        gmap = full_map({(x, y): yields(food=1) for x in range(20) for y in range(12)})
        rules = Rules()
        cfg = config.load(self.write("[objective.weights]\nfood = 4.0\n"))
        a = model.optimise(gmap, rules, n_cities=1, districts=(), improvements=())
        b = model.optimise(gmap, rules, cfg, n_cities=1, districts=(), improvements=())
        self.assertAlmostEqual(model.evaluate(gmap, rules, b)[0], 2 * model.evaluate(gmap, rules, a)[0])


if __name__ == "__main__":
    unittest.main()
