"""Contract regressions that can corrupt canvas choice or admit invalid delivery."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "prompt_tools.py"
spec = importlib.util.spec_from_file_location("prompt_tools", SCRIPT)
tools = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tools)


class PromptContractTests(unittest.TestCase):
    def test_near_square_uses_common_square(self):
        self.assertEqual(tools.describe_canvas(1040, 1000)["ratio"], "1:1")

    def test_portrait_and_landscape_remain_reciprocal(self):
        self.assertEqual(tools.describe_canvas(1080, 1920)["ratio"], "9:16")
        self.assertEqual(tools.describe_canvas(1920, 1080)["ratio"], "16:9")

    def test_explicit_target_overrides_dimensions(self):
        self.assertEqual(tools.describe_canvas(1040, 1000, "7:5")["ratio"], "7:5")

    def test_common_ratio_labels_are_preserved(self):
        for width, height in tools.COMMON_RATIOS:
            expected = f"{width}:{height}"
            self.assertEqual(tools.describe_canvas(width * 100, height * 100)["ratio"], expected)
        self.assertEqual(tools.describe_canvas(ratio="21:9")["ratio"], "21:9")

    def test_invalid_dimensions_fail(self):
        for width, height in ((0, 12), (-2, 3), (None, None), (True, 1)):
            with self.assertRaises(ValueError):
                tools.describe_canvas(width, height)

    def test_simple_image_does_not_require_padding(self):
        self.assertTrue(tools.validate_prompts({"zh": "1:1 纯白背景。", "en": "1:1 plain white canvas."}, "1:1")["ok"])

    def test_requested_single_language(self):
        self.assertTrue(tools.validate_prompts({"zh": "1:1 红圆"}, "1:1", language="zh")["ok"])
        self.assertTrue(tools.validate_prompts({"en": "1:1 red circle"}, "1:1", language="en")["ok"])
        self.assertFalse(tools.validate_prompts({"en": "1:1 red circle"}, "1:1", language="zh")["ok"])

    def test_unicode_and_whitespace_counting(self):
        result = tools.validate_prompts({"zh": "1:1 红 🌿\n白", "en": "1:1\nred\tleaf white"}, "1:1")
        self.assertEqual(result["counts"], {"zh": 6, "en": 4})

    def test_upper_limits_include_ratio(self):
        value = {"zh": "1:1" + "图" * 497, "en": "1:1 " + "red " * 499}
        self.assertTrue(tools.validate_prompts(value, "1:1")["ok"])
        for language in ("zh", "en"):
            overflow = dict(value)
            overflow[language] += " 多" if language == "zh" else " more"
            self.assertFalse(tools.validate_prompts(overflow, "1:1")["ok"])

    def test_missing_and_conflicting_ratios_fail(self):
        for english in ("square composition", "1:1 canvas with a 9:16 frame"):
            self.assertFalse(tools.validate_prompts({"zh": "1:1 红圆", "en": english}, "1:1")["ok"])

    def test_equivalent_ratios_are_accepted(self):
        self.assertTrue(tools.validate_prompts({"zh": "2：2 红圆", "en": "1:1 red circle"}, "1:1")["ok"])

    def test_pixels_require_explicit_override(self):
        value = {"zh": "1:1 白底", "en": "1:1 canvas, 1024x1024 pixels"}
        self.assertFalse(tools.validate_prompts(value, "1:1")["ok"])
        self.assertTrue(tools.validate_prompts(value, "1:1", allow_pixels=True)["ok"])

    def test_invalid_schema_fails(self):
        for value in ([], {"zh": "x"}, {"zh": 12, "en": "1:1"},
                      {"zh": "1:1", "en": " "}, {"zh": "1:1", "en": "1:1", "extra": 1}):
            self.assertFalse(tools.validate_prompts(value, "1:1")["ok"])

    def test_cli_stdin_exit_codes_and_duplicate_keys(self):
        command = [sys.executable, str(SCRIPT), "validate", "-", "--ratio", "1:1"]
        for payload, code in (({"zh": "1:1 红圆", "en": "1:1 red circle"}, 0),
                              ({"zh": "1:1 红圆", "en": "red circle"}, 1)):
            result = subprocess.run(command, input=json.dumps(payload), text=True, capture_output=True)
            self.assertEqual(result.returncode, code)
            self.assertEqual(json.loads(result.stdout)["ok"], code == 0)
        for invalid in ('{"zh":"1:1","zh":"1:1","en":"1:1"}', '{bad json'):
            result = subprocess.run(command, input=invalid, text=True, capture_output=True)
            self.assertEqual(result.returncode, 2)


if __name__ == "__main__":
    unittest.main()
