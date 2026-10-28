#!/usr/bin/env python3
"""Local canvas selection and prompt contract checks; no network or third-party packages."""
import argparse
import json
import math
import re
import sys
from fractions import Fraction
from pathlib import Path

COMMON_RATIOS = ((1, 1), (5, 4), (4, 3), (3, 2), (16, 9), (2, 1), (21, 9),
                 (4, 5), (3, 4), (2, 3), (9, 16))
RATIO_PATTERN = re.compile(r"(?<![\d.])([1-9]\d*)\s*[:：]\s*([1-9]\d*)(?![\d.])")
PIXEL_PATTERN = re.compile(r"(?<!\d)\d{2,5}\s*(?:×|x|by|\*)\s*\d{2,5}(?!\d)", re.I)


def positive_int(value):
    number = int(value)
    if number <= 0:
        raise ValueError("must be a positive integer")
    return number


def parse_ratio(value):
    match = re.fullmatch(r"\s*([1-9]\d*)\s*[:：]\s*([1-9]\d*)\s*", value)
    if not match:
        raise ValueError("ratio must contain positive integers, e.g. 1:1 or 4:5")
    return Fraction(int(match[1]), int(match[2]))


def describe_canvas(width=None, height=None, ratio=None):
    if ratio is not None:
        target = parse_ratio(ratio)
        ratio_label = re.sub(r"\s", "", ratio).replace("：", ":")
        source = "user"
    else:
        if type(width) is not int or type(height) is not int or width <= 0 or height <= 0:
            raise ValueError("provide positive integer width and height, or an explicit ratio")
        actual = math.log(width) - math.log(height)
        numerator, denominator = min(COMMON_RATIOS, key=lambda pair: abs(
            actual - math.log(pair[0] / pair[1])))
        target = Fraction(numerator, denominator)
        ratio_label = f"{numerator}:{denominator}"
        source = "dimensions"
    return {"ratio": ratio_label,
            "orientation": "square" if target == 1 else "landscape" if target > 1 else "portrait",
            "source": source}


def validate_prompts(value, ratio, zh_max=500, en_max=500, allow_pixels=False, language="both"):
    expected = parse_ratio(ratio)
    if zh_max <= 0 or en_max <= 0:
        raise ValueError("length limits must be positive")
    errors, counts = [], {}
    fields = {"zh", "en"} if language == "both" else {language}
    if not isinstance(value, dict) or set(value) != fields:
        return {"ok": False, "counts": {}, "errors": ["expected exactly " + ", ".join(sorted(fields)) + " fields"]}
    for language, limit in (("zh", zh_max), ("en", en_max)):
        if language not in fields:
            continue
        text = value[language]
        if not isinstance(text, str) or not text.strip():
            errors.append(f"{language}: expected a non-empty string")
            continue
        counts[language] = len(re.sub(r"\s", "", text)) if language == "zh" else len(text.split())
        if counts[language] > limit:
            errors.append(f"{language}: length {counts[language]} exceeds {limit}")
        found = [Fraction(int(m[1]), int(m[2])) for m in RATIO_PATTERN.finditer(text)]
        if expected not in found:
            errors.append(f"{language}: missing target ratio {ratio}")
        if any(item != expected for item in found):
            errors.append(f"{language}: conflicting aspect ratio; review before editing")
        if not allow_pixels and PIXEL_PATTERN.search(text):
            errors.append(f"{language}: pixel dimensions are disabled by default")
    return {"ok": not errors, "counts": counts, "errors": errors}


def load_json(path):
    def unique_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result
    content = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    return json.loads(content, object_pairs_hook=unique_keys)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    canvas = commands.add_parser("canvas", help="select common aspect ratio from displayed dimensions")
    canvas.add_argument("--width", type=positive_int)
    canvas.add_argument("--height", type=positive_int)
    canvas.add_argument("--ratio", help="explicit user target, overrides source dimensions")
    validate = commands.add_parser("validate", help="validate a bilingual prompt JSON file, or stdin (-)")
    validate.add_argument("file")
    validate.add_argument("--ratio", required=True)
    validate.add_argument("--zh-max", type=positive_int, default=500)
    validate.add_argument("--en-max", type=positive_int, default=500)
    validate.add_argument("--allow-pixels", action="store_true")
    validate.add_argument("--language", choices=("both", "zh", "en"), default="both")
    args = parser.parse_args(argv)
    try:
        if args.command == "canvas":
            output = describe_canvas(args.width, args.height, args.ratio)
        else:
            output = validate_prompts(load_json(args.file), args.ratio,
                                      args.zh_max, args.en_max, args.allow_pixels, args.language)
        print(json.dumps(output, ensure_ascii=False))
        return 0 if output.get("ok", True) else 1
    except (ValueError, OSError, OverflowError) as error:
        print(json.dumps({"ok": False, "errors": [str(error)]}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main())
