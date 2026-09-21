"""CLI entry point: extract a Form 8825 PDF into JSON.

Usage:
    uv run python -m form8825.cli task_input_files/f8825.pdf -o out.json
"""

from __future__ import annotations

import argparse
import json
import sys

from form8825.extract import ExtractionError, extract_pdf
from form8825.validate import validate_properties


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf_path", help="Path to the Form 8825 PDF")
    parser.add_argument("-o", "--output", help="Where to write the JSON (default: stdout)")
    args = parser.parse_args(argv)

    try:
        properties, warnings = extract_pdf(args.pdf_path)
    except ExtractionError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    for warning in warnings:
        target = f"property {warning.property_letter}" if warning.property_letter else "document"
        print(f"WARNING [{target}]: {warning.message}", file=sys.stderr)

    issues, grand_total_net_income = validate_properties(properties)
    for issue in issues:
        print(f"VALIDATION [{issue.property_name}]: {issue.message}", file=sys.stderr)
    print(
        f"Grand total net income across {len(properties)} propert"
        f"{'y' if len(properties) == 1 else 'ies'}: {grand_total_net_income:,}",
        file=sys.stderr,
    )

    output = json.dumps(properties, indent=2)
    if args.output:
        with open(args.output, "w") as f:
            f.write(output + "\n")
        print(f"Wrote {len(properties)} propert{'y' if len(properties) == 1 else 'ies'} to {args.output}", file=sys.stderr)
    else:
        print(output)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
