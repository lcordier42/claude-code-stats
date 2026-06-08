#!/usr/bin/env python3
"""Smoke test for the dashboard generator.

Runs extract_stats.py and asserts the output is well-formed. Catches the
regression classes we have actually hit: leftover locale placeholders, JS
syntax breaks (e.g. apostrophes in injected strings), locale key drift, and
"undefined" display artifacts.

Usage:  python3 test_smoke.py
Exit code 0 = all passed, 1 = a check failed.

Stdlib only. The JS syntax check needs `node` on PATH; it is skipped (with a
warning, not a failure) when node is unavailable.
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent
HTML = ROOT / "public" / "index.html"

failures = []
warnings = []


def check(name, ok, detail=""):
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] {name}" + (f" — {detail}" if detail and not ok else ""))
    if not ok:
        failures.append(name)


def main():
    print("Running extract_stats.py ...")
    run = subprocess.run(
        [sys.executable, "extract_stats.py"], cwd=ROOT,
        capture_output=True, text=True,
    )
    check("generator exits 0", run.returncode == 0, run.stderr[-500:])
    check("generator reports Done", "Done in" in run.stdout, "no 'Done in' line")
    check("index.html exists", HTML.exists())
    if not HTML.exists():
        _finish()
        return

    html = HTML.read_text(encoding="utf-8")

    # No unresolved locale placeholders (e.g. __L_rtk_kpi_saved__)
    leftover = sorted(set(re.findall(r"__L_[a-z0-9_]+__", html)))
    check("no leftover __L_ placeholders", not leftover, ", ".join(leftover[:5]))

    # No "undefined" display artifacts in rendered text (">undefined<" / "undefined MB")
    artifacts = re.findall(r">undefined<|undefined MB|undefined%", html)
    check("no 'undefined' display artifacts", not artifacts, f"{len(artifacts)} found")

    # Locale key parity across all locale files
    _check_locale_parity()

    # JS syntax check via node (skipped if node missing)
    _check_js_syntax(html)

    _finish()


def _check_locale_parity():
    def keys(d, prefix=""):
        out = set()
        for k, v in d.items():
            kp = f"{prefix}.{k}" if prefix else k
            out.add(kp)
            if isinstance(v, dict):
                out |= keys(v, kp)
        return out

    locales = sorted((ROOT / "locales").glob("*.json"))
    if not locales:
        check("locale files present", False, "none found")
        return
    ref = json.loads(locales[0].read_text(encoding="utf-8"))
    ref_keys = keys(ref)
    all_ok = True
    detail = []
    for lf in locales[1:]:
        k = keys(json.loads(lf.read_text(encoding="utf-8")))
        miss, extra = ref_keys - k, k - ref_keys
        if miss or extra:
            all_ok = False
            detail.append(f"{lf.name}: -{sorted(miss)} +{sorted(extra)}")
    check(f"locale key parity ({len(locales)} files vs {locales[0].name})", all_ok, "; ".join(detail))


def _check_js_syntax(html):
    if not shutil.which("node"):
        warnings.append("node not found — skipped JS syntax check")
        print("  [SKIP] JS syntax check (node not on PATH)")
        return
    scripts = re.findall(r"<script>(.*?)</script>", html, re.S)
    js = "\n".join(scripts).replace("const D = ", "const D = {};//")
    stub = (
        "const document={getElementById:()=>null,querySelectorAll:()=>[],"
        "querySelector:()=>null,createElement:()=>({appendChild(){},"
        "classList:{add(){},remove(){},toggle(){}},style:{},addEventListener(){},"
        "setAttribute(){}}),addEventListener(){},body:{classList:{toggle(){}}}};"
        "const window={};const Chart=function(){};Chart.register=()=>{};\n"
    )
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(stub + js)
        tmp = f.name
    res = subprocess.run(["node", "--check", tmp], capture_output=True, text=True)
    check("inlined JS passes node --check", res.returncode == 0, res.stderr.strip()[-300:])


def _finish():
    print()
    for w in warnings:
        print(f"  ⚠ {w}")
    if failures:
        print(f"\n❌ {len(failures)} check(s) failed: {', '.join(failures)}")
        sys.exit(1)
    print("\n✅ All checks passed.")
    sys.exit(0)


if __name__ == "__main__":
    main()
