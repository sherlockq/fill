# Fill

Render Jinja2 templates with YAML/CSV data.

Optionally **batching** and a **batch-sql** preprocessor could convert one-row (or multi-row) `INSERT ... VALUES ...;`
statements into batched, comma-safe multi-row inserts.

## Features

- Input: **YAML** or **CSV**
- Output modes:
    - `one-file`: concatenate renders with a Jinja-enabled separator
    - `multiple-files`: `output_1.txt`, `output_2.txt`, …
- `--batch N`: render once per batch with `batch` (list of row dicts) in context
- `--preprocess batch-sql`: wrap the **entire** `VALUES …` block in a Jinja loop, using a **list + join** pattern (
  comma-safe even when skipping rows with `{% continue %}`)
- Jinja **extensions enabled**: `loopcontrols` (`{% break %}`, `{% continue %}`) and `do`

## Usage

Install as CLI to execute anywhere

```bash
pip install .

fill --help
```

Or without installing as a CLI tool

```bash
python src/fill/cli.py --help

python src/fill/cli.py \
  --template inserts.sql.j2 \
  --values data.csv \
  --output out.sql \
  --output-mode one-file \
  --preprocess batch-sql \
  --batch 1000 \
  --separator "\n-- batch {{batch_index}} (rows {{start_index}}-{{end_index}}/{{total}})\n"
  ```

### Arguments

- --template (required): Path to your Jinja template.
- --values (required): Path to .yaml/.yml or .csv.
- --output (required): File path (for one-file) or directory (for multiple-files).
- --output-mode (required): one-file or multiple-files.
- --separator (optional): Jinja-enabled string for one-file mode (default \n--{{index}}-\n\n).
- --batch (optional): Batch size (e.g. 1000). If omitted, default behavior renders once per row.
- --preprocess (optional): none (default) or batch-sql.

### Data formats

CSV: headers form the keys.

```csv
case_number,productcode
1001,PC-A
1002,PC-B
```

YAML:

```yaml
# either a list:
- case_number: "1001"
  productcode: "PC-A"
- case_number: "1002"
  productcode: "PC-B"

# or a dict with a top-level list key like rows/items/data/values:
rows:
  - case_number: "1001"
    productcode: "PC-A"
  - case_number: "1002"
    productcode: "PC-B"
```

### How --preprocess batch-sql works

Given a template:

```sql
INSERT INTO A (id, created, updated, key)
VALUES ('id-{{case_number}}', now(), now(), 0, '{{case_number}}-1');

INSERT INTO other (id, created, updated)
VALUES (uuid(), now(), now());
```

It becomes internally:

```jinja2
INSERT INTO A (id, created, updated, key) VALUES
{%- set __tuples = [] -%}
{%- for row in batch %}
  {%- set __t -%}
('id-{{ row.case_number }}', now(), now(), 0, '{{ row.case_number }}-1')
  {%- endset -%}
  {%- do __tuples.append(__t | trim) -%}
{%- endfor -%}
{{ __tuples | join(',\n') }};

INSERT INTO other (id, created, updated) VALUES
{%- set __tuples = [] -%}
{%- for row in batch %}
  {%- set __t -%}
(uuid(), now(), now())
  {%- endset -%}
  {%- do __tuples.append(__t | trim) -%}
{%- endfor -%}
{{ __tuples | join(',\n') }};
```

- It repeats the entire VALUES … segment per row.
- All {{var}} inside that segment are rewritten to {{ row.var }}.
- Commas are inserted by join, so there’s no trailing comma even if you {% continue %} some rows.

It's possible to add Jinja logic statements to the original template file around the values tuples, with access to
variable `row` which stands for each data record. This will make the template file incompatible without batching and
batch-sql processor.

```jinja2
insert into A (field_1, field_2) values
{% if row.ignored %}
    {% continue %}
{% else %}
    {% if row.type and row.type == 'X' %}
    ('type-X', '{{row.X_value}}')
    {% else %}
    ('type-Y', '{{row.X_value}}')
    {% endif %}
{% endif %}
;

```

### Tips

- You can use {% continue %} / {% break %} safely (thanks to loopcontrols).
- If you want to skip rows and keep commas correct, the join pattern used by the preprocessor already handles it.
- To run output into MySQL:

```bash
mysql -u user -p dbname < out.sql
```

or concatenate multiple batch files and pipe them in.

## Development

Run unit tests:

```bash
pytest -q
```

Run quick smoke demo:

```bash
bash scripts/run_examples.sh
```
