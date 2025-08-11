import csv
import textwrap
from pathlib import Path

from fill.processor import preprocess_batch_sql, get_env
from fill.utils import load_values, write_outputs


def test_preprocess_wraps_entire_values_block_and_prefixes_vars():
    src = textwrap.dedent("""
                          INSERT INTO A (id) VALUES ('1'), ('2');
                          INSERT INTO B (a,b) VALUES ({{a}}, {{b}}), ({{a}}, {{b}});
                          """).strip()

    out = preprocess_batch_sql(src)

    # Loop scaffolding exists
    assert "{%- set __tuples = [] -%}" in out
    assert "{%- for row in batch %}" in out
    assert "{%- endfor -%}" in out
    assert "{{ __tuples | join(',\\n') }}" in out

    # Entire VALUES segment kept as a block inside loop
    assert "('1'), ('2')" in out

    # Var prefixing inside VALUES to row.*
    assert "{{ row.a }}" in out
    assert "{{ row.b }}" in out
    assert "{{a}}" not in out
    assert "{{b}}" not in out


def test_preprocess_leaves_insert_select_unchanged():
    src = "INSERT INTO t (a) SELECT 1;"
    out = preprocess_batch_sql(src)
    assert out == src


def test_join_pattern_is_comma_safe_with_continue():
    env = get_env()
    # Template simulates output of preprocess and uses continue
    tpl = textwrap.dedent("""
                          INSERT INTO T (id) VALUES
                              {%- set __tuples = [] -%}
                              {%- for row in batch %}
                              {%- if row.skip %}{% continue %}{% endif %}
                              {%- set __t -%}
                              ('{{ row.id }}')
                              {%- endset -%}
            {%- do __tuples.append(__t | trim) -%}
                              {%- endfor -%}
                              {{ __tuples | join(',\\n') }};
                          """).strip()

    t = env.from_string(tpl)
    out = t.render({"batch": [
        {"id": 1, "skip": False},
        {"id": 2, "skip": True},   # skipped
        {"id": 3, "skip": False}
    ]})

    # Should produce two tuples, comma between them, no trailing comma
    assert "('1')" in out
    assert "('3')" in out
    assert "('2')" not in out
    assert ",\n" in out
    assert out.strip().endswith(";")


def test_end_to_end_batch_sql_preprocess_and_render():
    env = get_env()
    src = textwrap.dedent("""
                          INSERT INTO owner (id, name) VALUES ('ihs-{{mortgage_number}}', '{{productcode}}');
                          INSERT INTO other (id, created, updated) VALUES (uuid(), now(), now());
                          """).strip()

    pre = preprocess_batch_sql(src)
    t = env.from_string(pre)

    batch = [
        {"mortgage_number": "1001", "productcode": "PC-A"},
        {"mortgage_number": "1002", "productcode": "PC-B"},
    ]
    out = t.render({"batch": batch})

    # owner rows repeated twice with comma between
    assert "('ihs-1001', 'PC-A')" in out
    assert "('ihs-1002', 'PC-B')" in out
    # other rows repeated twice with comma between
    assert out.count("(uuid(), now(), now())") == 2
    # ends with a single semicolon
    assert out.strip().endswith(";")


def test_write_outputs_one_file(tmp_path: Path):
    env = get_env()
    outputs = ["A", "B", "C"]
    contexts = [{"batch_index": 1}, {"batch_index": 2}, {"batch_index": 3}]
    out_file = tmp_path / "combined.txt"

    write_outputs(
        outputs=outputs,
        contexts=contexts,
        output_path=str(out_file),
        mode="one-file",
        separator_template="\n--{{index}}--\n",
        env=env,
    )
    text = out_file.read_text(encoding="utf-8")
    assert "--1--" in text and "--2--" in text and "--3--" in text
    for token in outputs:
        assert token in text


def test_write_outputs_multiple_files(tmp_path: Path):
    env = get_env()
    outputs = ["foo", "bar"]
    contexts = [{}, {}]
    out_dir = tmp_path / "outdir"

    write_outputs(
        outputs=outputs,
        contexts=contexts,
        output_path=str(out_dir),
        mode="multiple-files",
        separator_template="IGNORED",
        env=env,
    )

    files = sorted(out_dir.glob("output_*.txt"))
    assert len(files) == 2
    assert files[0].read_text(encoding="utf-8") == "foo"
    assert files[1].read_text(encoding="utf-8") == "bar"


def test_csv_and_yaml_loading(tmp_path: Path):
    # YAML list
    from fill.utils import load_values  # re-import to avoid shadowing above
    y1 = tmp_path / "rows.yaml"
    y1.write_text(textwrap.dedent("""
        - a: 1
          b: x
        - a: 2
          b: y
    """).strip() + "\n", encoding="utf-8")
    assert load_values(str(y1)) == [{"a": 1, "b": "x"}, {"a": 2, "b": "y"}]

    # YAML dict with rows key
    y2 = tmp_path / "rows2.yaml"
    y2.write_text(textwrap.dedent("""
        rows:
          - x: u
          - x: v
    """).strip() + "\n", encoding="utf-8")
    assert load_values(str(y2)) == [{"x": "u"}, {"x": "v"}]

    # CSV
    c = tmp_path / "rows.csv"
    with c.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["a", "b"])
        w.writerow([1, "x"])
        w.writerow([2, "y"])
    assert load_values(str(c)) == [{"a": "1", "b": "x"}, {"a": "2", "b": "y"}]

# add to tests/test_fill.py
import os
import sys
import subprocess
import textwrap

def test_cli_smoke_python_m_fill(tmp_path):
    # create a tiny template with two INSERTs
    tpl = tmp_path / "tpl.sql.j2"
    tpl.write_text(textwrap.dedent("""
                                   INSERT INTO owner (id, name) VALUES ('{{case_number}}', '{{productcode}}');
                                   INSERT INTO other (id, created, updated) VALUES (uuid(), now(), now());
                                   """).strip() + "\n", encoding="utf-8")

    # create CSV with 3 rows
    csvf = tmp_path / "rows.csv"
    csvf.write_text(textwrap.dedent("""
        case_number,productcode
        1001,PC-A
        1002,PC-B
        1003,PC-C
    """).strip() + "\n", encoding="utf-8")

    out = tmp_path / "out.sql"

    # run: python -m fill ...  (without installing)
    # ensure subprocess can import from src/ by setting PYTHONPATH
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    env = dict(os.environ)
    env["PYTHONPATH"] = os.path.join(project_root, "src")

    cmd = [
        sys.executable, "-m", "fill",
        "--template", str(tpl),
        "--values", str(csvf),
        "--output", str(out),
        "--output-mode", "one-file",
        "--preprocess", "batch-sql",
        "--batch", "2",
        "--separator", "\n-- batch {{batch_index}} ({{start_index}}..{{end_index}}/{{total}})\n",
    ]
    res = subprocess.run(cmd, env=env, capture_output=True, text=True)
    assert res.returncode == 0, f"stderr:\n{res.stderr}\nstdout:\n{res.stdout}"

    content = out.read_text(encoding="utf-8")

    # We rendered 2 batches, so both INSERT statements should appear twice.
    assert content.count("INSERT INTO owner") == 2
    assert content.count("INSERT INTO other") == 2

    # Rows 1001 & 1002 should be in the first batch block, 1003 in the second.
    assert "('1001', 'PC-A')" in content
    assert "('1002', 'PC-B')" in content
    assert "('1003', 'PC-C')" in content

    # Our separator should show batch indices 1 and 2
    assert "-- batch 1 (1..2/3)" in content
    assert "-- batch 2 (3..3/3)" in content

    # Should end cleanly with a trailing separator (by current design) or not—allow either.
    assert content.strip(), "Output file is empty"
