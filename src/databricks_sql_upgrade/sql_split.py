"""Split SQL scripts into individual statements."""

from __future__ import annotations

import re


def strip_block_comments(sql: str) -> str:
    return re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)


def split_sql_statements(sql: str) -> list[str]:
    """Split on semicolons outside of single-quoted strings."""
    sql = strip_block_comments(sql)
    statements: list[str] = []
    current: list[str] = []
    in_single = False
    i = 0
    while i < len(sql):
        ch = sql[i]
        if ch == "'" and not in_single:
            in_single = True
            current.append(ch)
        elif ch == "'" and in_single:
            if i + 1 < len(sql) and sql[i + 1] == "'":
                current.append("''")
                i += 1
            else:
                in_single = False
                current.append(ch)
        elif ch == ";" and not in_single:
            stmt = "".join(current).strip()
            if stmt and not _is_comment_only(stmt):
                statements.append(stmt)
            current = []
        else:
            current.append(ch)
        i += 1
    tail = "".join(current).strip()
    if tail and not _is_comment_only(tail):
        statements.append(tail)
    return statements


def _is_comment_only(stmt: str) -> bool:
    lines = [ln.strip() for ln in stmt.splitlines() if ln.strip()]
    return bool(lines) and all(ln.startswith("--") for ln in lines)
