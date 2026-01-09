#!/usr/bin/env python3
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "com.frogtosea.tinyPrint.apk_Decompiler.com" / "sources" / "com" / "Utils" / "PrintModelUtils.java"
OUT = ROOT / "emx_040256_printer" / "timiniprint" / "data" / "printer_models.json"

CONSTANTS = {
    "OS2WindowsMetricsTable.WEIGHT_CLASS_LIGHT": 300,
    "OS2WindowsMetricsTable.WEIGHT_CLASS_MEDIUM": 500,
    "OS2WindowsMetricsTable.WEIGHT_CLASS_BOLD": 700,
    "OS2WindowsMetricsTable.WEIGHT_CLASS_EXTRA_BOLD": 800,
    "OS2WindowsMetricsTable.WEIGHT_CLASS_BLACK": 900,
    "Shape.MASTER_DPI": 576,
    "BannerConfig.LOOP_TIME": 3000,
    "AccessibilityNodeInfoCompat.EXTRA_DATA_TEXT_CHARACTER_LOCATION_ARG_MAX_LENGTH": 20000,
    "PDLayoutAttributeObject.GLYPH_ORIENTATION_VERTICAL_ZERO_DEGREES": "0",
}


def extract_args(text: str, start: int) -> str:
    depth = 1
    i = start
    in_str = False
    esc = False
    while i < len(text):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
                if depth == 0:
                    return text[start:i]
        i += 1
    raise ValueError("No closing paren found")


def split_args(arg_str: str) -> list[str]:
    args = []
    cur = []
    depth = 0
    in_str = False
    esc = False
    for ch in arg_str:
        if in_str:
            cur.append(ch)
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
                cur.append(ch)
            elif ch in "([{":
                depth += 1
                cur.append(ch)
            elif ch in ")]}":
                depth -= 1
                cur.append(ch)
            elif ch == ',' and depth == 0:
                args.append(''.join(cur).strip())
                cur = []
            else:
                cur.append(ch)
    if cur:
        args.append(''.join(cur).strip())
    return args


def parse_token(tok: str):
    tok = tok.strip()
    if tok.startswith("(int) "):
        tok = tok[len("(int) ") :].strip()
    elif tok.startswith("(float) "):
        tok = tok[len("(float) ") :].strip()
    elif tok.startswith("(double) "):
        tok = tok[len("(double) ") :].strip()
    if tok in CONSTANTS:
        return CONSTANTS[tok]
    if tok == "true":
        return True
    if tok == "false":
        return False
    if tok.startswith('"') and tok.endswith('"'):
        return tok[1:-1]
    if re.match(r"^-?\d+\.\d+[df]$", tok):
        return float(tok[:-1])
    if re.match(r"^-?\d+\.\d+$", tok):
        return float(tok)
    if re.match(r"^-?\d+$", tok):
        return int(tok)
    raise ValueError(f"Unknown token: {tok}")


def main() -> None:
    text = SOURCE.read_text(encoding="utf-8")
    pattern = re.compile(r"new\s+PrinterModel\.DataBean\(")
    starts = [m.end() for m in pattern.finditer(text)]
    models = []

    for start in starts:
        args_str = extract_args(text, start)
        raw_args = split_args(args_str)
        args = [parse_token(tok) for tok in raw_args]
        if len(args) < 25:
            raise ValueError(f"Unexpected arg count: {len(args)} for {raw_args[:3]}")

        model = {
            "model_no": args[0],
            "model": int(args[1]),
            "size": int(args[2]),
            "paper_size": int(args[3]),
            "print_size": int(args[4]),
            "one_length": int(args[5]),
            "head_name": args[6],
            "can_change_mtu": bool(args[7]),
            "dev_dpi": int(args[8]),
            "img_print_speed": int(args[9]),
            "text_print_speed": int(args[10]),
            "img_mtu": int(args[11]),
            "new_compress": bool(args[12]),
            "paper_num": int(args[13]),
            "interval_ms": int(args[14]),
            "thin_energy": int(args[15]),
            "moderation_energy": int(args[16]),
            "deepen_energy": int(args[17]),
            "text_energy": int(args[18]),
            "has_id": bool(args[19]),
            "use_spp": bool(args[20]),
            "new_format": bool(args[21]),
            "can_print_label": bool(args[22]),
            "label_value": str(args[23]),
            "back_paper_num": int(args[24]),
            "a4xii": False,
            "add_mor_pix": None,
        }

        # A4XII models are the only ones using the signature that ends with two booleans.
        if len(args) == 29 and isinstance(args[-1], bool) and isinstance(args[-2], bool):
            model["add_mor_pix"] = args[-2]
            model["a4xii"] = args[-1]

        models.append(model)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(models, indent=2, ensure_ascii=True), encoding="utf-8")
    print(f"Wrote {len(models)} models to {OUT}")


if __name__ == "__main__":
    main()
