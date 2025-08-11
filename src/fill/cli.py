#!/usr/bin/env python3
import argparse

# --- allow running as a script: `python src/fill/cli.py ...` without installing ---
# This adds the project `src/` directory to sys.path at runtime.
import sys
from pathlib import Path
_THIS_FILE = Path(__file__).resolve()
_SRC_DIR = _THIS_FILE.parents[1]  # .../src
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))
# -------------------------------------------------------------------------------

from fill.processor import get_env, preprocess_batch_sql  # noqa: E402
from fill.utils import load_values, write_outputs, chunked  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="Render a Jinja2 template using YAML or CSV input.")
    parser.add_argument("--template", required=True, help="Path to the template file.")
    parser.add_argument("--values", required=True, help="Path to the YAML or CSV values file.")
    parser.add_argument("--output", required=True, help="Output file (for one-file) or directory (for multiple-files).")
    parser.add_argument("--output-mode", choices=["one-file", "multiple-files"], required=True, help="Choose output mode.")
    parser.add_argument("--separator", default="\n--{{index}}-\n\n", help="Jinja2-enabled separator for one-file output. Can use {{index}}, etc.")
    parser.add_argument("--batch", type=int, default=0, help="Batch size. If set, render once per batch with 'batch' in context.")
    parser.add_argument("--preprocess", choices=["none", "batch-sql"], default="none",
                        help="Preprocess template before rendering. 'batch-sql' wraps the entire VALUES segment into a join-based Jinja loop.")
    args = parser.parse_args()

    separator = args.separator.encode('utf-8').decode('unicode_escape')
    env = get_env()

    with open(args.template, "r", encoding="utf-8") as f:
        template_text = f.read()

    if args.preprocess == "batch-sql":
        template_text = preprocess_batch_sql(template_text)
        if not args.batch or args.batch <= 0:
            args.batch = 10**12  # effectively infinite

    template = env.from_string(template_text)
    values_list = load_values(args.values) or []

    if not args.batch or args.batch <= 0:
        outputs = [template.render({**values, "index": i}) for i, values in enumerate(values_list, start=1)]
        contexts = [dict(values, **{"index": i}) if isinstance(values, dict) else {"index": i}
                    for i, values in enumerate(values_list, start=1)]
        write_outputs(outputs, contexts, args.output, args.output_mode, separator, env)
        return

    total = len(values_list)
    outputs, contexts = [], []

    enriched = []
    for i, row in enumerate(values_list, start=1):
        r = dict(row) if isinstance(row, dict) else {"value": row}
        r.setdefault("index", i)
        enriched.append(r)

    for bidx, (start0, batch_rows) in enumerate(chunked(enriched, args.batch), start=1):
        rows_in_batch = []
        for j, r in enumerate(batch_rows, start=1):
            rr = dict(r)
            rr["row_index"] = j
            rows_in_batch.append(rr)

        start_index = start0 + 1
        end_index = start0 + len(batch_rows)

        ctx = {
            "batch": rows_in_batch,
            "batch_index": bidx,
            "start_index": start_index,
            "end_index": end_index,
            "total": total
        }
        rendered = template.render(ctx)
        outputs.append(rendered)
        contexts.append({
            "batch_index": bidx,
            "size": len(rows_in_batch),
            "start_index": start_index,
            "end_index": end_index,
            "total": total,
            "index": bidx
        })

    write_outputs(outputs, contexts, args.output, args.output_mode, separator, env)


if __name__ == "__main__":
    main()
