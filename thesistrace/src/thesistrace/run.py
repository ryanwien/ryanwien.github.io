"""End-to-end run: build the sample note through the store, summarise it, write ``results/``.

``python -m thesistrace.run`` regenerates ``results/metrics.json`` and
``results/REPORT.md``. Output is byte-identical between runs.
"""

import ast
import json
from pathlib import Path
from typing import Final

from thesistrace.report import markdown, metrics
from thesistrace.scenario import seed
from thesistrace.store import NoteStore
from thesistrace.summary import summarize

PROJECT_DIR: Final = Path(__file__).resolve().parents[2]
RESULTS_DIR: Final = PROJECT_DIR / "results"
TESTS_DIR: Final = PROJECT_DIR / "tests"


def count_tests(tests_dir: Path = TESTS_DIR) -> int:
    """Count ``test_*`` functions by parsing the test files (no pytest run needed)."""
    total = 0
    for path in sorted(tests_dir.glob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        total += sum(
            1
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
        )
    return total


def _write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    store = NoteStore()
    note = seed(store)
    summary = summarize(note)
    tests = count_tests()
    RESULTS_DIR.mkdir(exist_ok=True)
    _write_json(RESULTS_DIR / "metrics.json", metrics(note, summary, tests))
    (RESULTS_DIR / "REPORT.md").write_text(markdown(note, summary), encoding="utf-8")
    print(f"{summary.headline} ({summary.total} assumptions, {tests} tests)")
    print(f"wrote {RESULTS_DIR}")


if __name__ == "__main__":
    main()
