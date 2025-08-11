import csv
import os
from typing import List, Dict, Any, Iterable, Tuple
import yaml
from jinja2 import Environment

def load_values(values_file: str) -> List[Dict[str, Any]]:
    if values_file.endswith((".yaml", ".yml")):
        with open(values_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            if isinstance(data, dict):
                for k in ("rows", "items", "data", "values"):
                    if k in data and isinstance(data[k], list):
                        return data[k]
                return [data]
            return data
    elif values_file.endswith(".csv"):
        with open(values_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            return list(reader)
    else:
        raise ValueError("Unsupported input file format. Use .yaml, .yml, or .csv")

def render_separator(env: Environment, template_str: str, context: Dict[str, Any]) -> str:
    return env.from_string(template_str).render(context)

def write_outputs(
        outputs: Iterable[str],
        contexts: Iterable[Dict[str, Any]],
        output_path: str,
        mode: str,
        separator_template: str,
        env: Environment,
) -> None:
    outputs = list(outputs)
    contexts = list(contexts)
    if mode == "one-file":
        combined = ""
        for i, (rendered, ctx) in enumerate(zip(outputs, contexts), start=1):
            context = dict(ctx or {})
            context["index"] = i  # keep {{index}} available in separator
            sep = render_separator(env, separator_template, context)
            combined += rendered + sep
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(combined)
        print(f"✅ Wrote combined output to: {output_path}")

    elif mode == "multiple-files":
        os.makedirs(output_path, exist_ok=True)
        for i, (rendered, _ctx) in enumerate(zip(outputs, contexts), start=1):
            filename = f"output_{i}.txt"
            file_path = os.path.join(output_path, filename)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(rendered)
        print(f"✅ Wrote {len(outputs)} files to: {output_path}/")
    else:
        raise ValueError("Invalid output mode. Use 'one-file' or 'multiple-files'.")

def chunked(seq: List[Dict[str, Any]], n: int) -> Iterable[Tuple[int, List[Dict[str, Any]]]]:
    for i in range(0, len(seq), n):
        yield i, seq[i:i+n]
