"""
Extract coverage info from a pytest-cov JSON report.

- For each file: total number of covered lines
- For each function: percentage of lines covered

Usage:
    python extract_cov.py coverage.json
"""

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path, help="Path to pytest-cov JSON report")
    parser.add_argument(
        "--include-module",
        action="store_true",
        help="Include unnamed ('') module-level entries as functions",
    )
    args = parser.parse_args()

    with args.report.open("r", encoding="utf-8") as f:
        data = json.load(f)

    files = data.get("files", {})

    for filename, fdata in files.items():
        if "tests/" in filename:
            # Skip test files
            continue
        summary = fdata.get("summary", {})
        covered_lines = summary.get("covered_lines")

        print(f"\nFile: {filename}")
        print(f"  Covered lines (file total): {covered_lines}")

        functions = fdata.get("functions", {})
        if not functions:
            continue

        print("  Function coverage:")
        for func_name, func_data in functions.items():
            # pytest-cov uses "" for module-level code
            if not args.include_module and func_name == "":
                continue

            func_summary = func_data.get("summary", {})
            pct = func_summary.get("percent_covered")

            # Handle None or missing values gracefully
            if pct is None:
                pct_str = "N/A"
            else:
                # Keep as-is (already a float) or pretty-print if you like:
                pct_str = f"{pct:.2f}"

            display_name = func_name if func_name else "<module>"
            print(f"    {display_name}: {pct_str}%")

    # If you also want overall totals, you can uncomment this:
    totals = data.get("totals", {})
    print("\nOverall totals:")
    print(f"  Covered lines: {totals.get('covered_lines')}")
    # print(f"  Num statements: {totals.get('num_statements')}")
    print(f"  Percent covered: {totals.get('percent_covered')}")


if __name__ == "__main__":
    main()
