import re
from jinja2 import Environment, BaseLoader

# Build a shared Jinja environment with the needed extensions
def get_env() -> Environment:
    return Environment(
        loader=BaseLoader(),
        trim_blocks=True,
        lstrip_blocks=True,
        extensions=["jinja2.ext.loopcontrols", "jinja2.ext.do"],
    )

# --- preprocess: batch-sql (repeat entire VALUES block, comma-safe) ---

# matches {{ something | filters }}
_VAR_RE = re.compile(r"{{\s*([^}\s|]+(?:\.[^}\s|]+)*)\s*(\|[^}]*)?}}")

def _prefix_row_in_segment(segment: str) -> str:
    """
    Add 'row.' in front of bare Jinja vars inside the VALUES segment.
    Leaves names already starting with row., function-ish, or numeric untouched.
    """
    def repl(m):
        name = m.group(1).strip()
        filters = m.group(2) or ""
        if name.startswith("row.") or "(" in name or name.replace("_", "").isdigit():
            return "{{ " + name + filters + " }}"
        return "{{ row." + name + filters + " }}"
    return _VAR_RE.sub(repl, segment)

def preprocess_batch_sql(template_text: str) -> str:
    """
    For every:
        INSERT ... VALUES <values-segment> ;
    transform to a comma-safe loop using a collection + join:
        INSERT ... VALUES
        {%- set __tuples = [] -%}
        {%- for row in batch %}
          {%- set __t -%}
          <values-segment-with-{{row.*}}>
          {%- endset -%}
          {%- do __tuples.append(__t | trim) -%}
        {%- endfor -%}
        {{ __tuples | join(',\\n') }};
    The entire VALUES segment (which may contain multiple tuples) is repeated as a block for each row.
    """
    ins_re = re.compile(r"(INSERT\s+INTO\s+.*?\bVALUES\b)(.*?);", re.IGNORECASE | re.DOTALL)

    def transform(m):
        head = m.group(1)          # "INSERT ... VALUES"
        values_seg = m.group(2)    # everything after VALUES up to before ';'
        if not values_seg.strip():
            return m.group(0)

        values_seg_prefixed = _prefix_row_in_segment(values_seg)

        loop_block = (
            "\n    {%- set __tuples = [] -%}\n"
            "    {%- for row in batch %}\n"
            "      {%- set __t -%}\n"
            f"{values_seg_prefixed}\n"
            "      {%- endset -%}\n"
            "      {%- do __tuples.append(__t | trim) -%}\n"
            "    {%- endfor -%}\n"
            "    {{ __tuples | join(',\\n') }}\n"
        )
        return head + loop_block + ";"

    return ins_re.sub(transform, template_text)
