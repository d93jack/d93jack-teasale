import importlib.util
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("generate_report", ROOT / "src" / "generate_report.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class ProjectTests(unittest.TestCase):
    def test_formal_pool_has_exactly_40_exposures(self):
        universe = json.loads((ROOT / "config" / "universe.json").read_text(encoding="utf-8"))
        self.assertEqual(len(universe["formal_exposures"]), 40)

    def test_tsm_is_one_exposure(self):
        universe = json.loads((ROOT / "config" / "universe.json").read_text(encoding="utf-8"))
        symbols = [item["symbol"] for item in universe["formal_exposures"]]
        self.assertEqual(symbols.count("TSM/2330"), 1)
        self.assertNotIn("TSM", symbols)
        self.assertNotIn("2330", symbols)

    def test_dram_etf_is_in_formal_pool(self):
        universe = json.loads((ROOT / "config" / "universe.json").read_text(encoding="utf-8"))
        dram = next(item for item in universe["formal_exposures"] if item["symbol"] == "DRAM")
        self.assertEqual(dram["asset_type"], "ETF")

    def test_sunday_event_parser(self):
        self.assertRegex("MAJOR_EVENT: YES\n證據", r"^MAJOR_EVENT:\s*YES\b")
        self.assertNotRegex("MAJOR_EVENT: NO\n沒有", r"^MAJOR_EVENT:\s*YES\b")

    def test_workflow_has_four_taipei_schedules(self):
        workflow = (ROOT / ".github" / "workflows" / "main.yml").read_text(encoding="utf-8")
        for cron in ("15 7 * * 1-5", "15 19 * * 1-5", "0 11 * * 6", "30 8 * * 0"):
            self.assertIn(cron, workflow)
        self.assertEqual(workflow.count('timezone: "Asia/Taipei"'), 4)
        self.assertIn("secrets.OPENAI_API_KEY", workflow)

    def test_prompt_contains_locked_risk_rules(self):
        prompt = (ROOT / "prompts" / "report_prompt.md").read_text(encoding="utf-8")
        for phrase in ("最大可接受組合回撤15%", "長期核心55%", "Risk-off", "Serenity七問", "Roundhill Memory ETF"):
            self.assertIn(phrase, prompt)


if __name__ == "__main__":
    unittest.main()
