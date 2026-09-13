"""The three brief questions as named SQL (L4, A2), read from queries.sql next to this file."""

from __future__ import annotations

import re
from pathlib import Path

QUERIES_SQL = Path(__file__).with_name("queries.sql")


def named_queries(path: Path = QUERIES_SQL) -> dict[str, str]:
    """Parse `-- name: x` blocks from queries.sql."""
    out, name, buf = {}, None, []
    for line in path.read_text().splitlines():
        m = re.match(r"--\s*name:\s*(\w+)", line)
        if m:
            if name:
                out[name] = "\n".join(buf).strip()
            name, buf = m.group(1), []
        elif name and not line.startswith("--"):
            buf.append(line)
    if name:
        out[name] = "\n".join(buf).strip()
    return out
