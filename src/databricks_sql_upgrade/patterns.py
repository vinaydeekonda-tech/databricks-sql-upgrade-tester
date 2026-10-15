"""SQL pattern and function definitions for Databricks SQL upgrade scanning."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class SqlPattern:
    name: str
    category: str
    risk: str
    regex: str
    description: str


# High-risk constructs that frequently break across Databricks SQL runtime upgrades.
SQL_PATTERNS: tuple[SqlPattern, ...] = (
    SqlPattern("MERGE", "dml", "high", r"\bMERGE\s+INTO\b", "Delta MERGE INTO"),
    SqlPattern("UPDATE", "dml", "high", r"\bUPDATE\b", "UPDATE statements"),
    SqlPattern("DELETE", "dml", "high", r"\bDELETE\s+FROM\b", "DELETE FROM"),
    SqlPattern("INSERT_OVERWRITE", "dml", "medium", r"\bINSERT\s+OVERWRITE\b", "INSERT OVERWRITE"),
    SqlPattern("DECLARE", "scripting", "high", r"\bDECLARE\b", "DECLARE variables"),
    SqlPattern("SET_VAR", "scripting", "high", r"\bSET\s+(?:VAR|VARIABLE)\b", "SET variable"),
    SqlPattern("TEMP_VIEW", "ddl", "high", r"\bCREATE\s+(?:OR\s+REPLACE\s+)?TEMPORARY\s+VIEW\b", "Temporary views"),
    SqlPattern("QUALIFY", "analytics", "high", r"\bQUALIFY\b", "QUALIFY window filter"),
    SqlPattern("WINDOW", "analytics", "medium", r"\bWINDOW\b", "Named WINDOW clause"),
    SqlPattern("PIVOT", "analytics", "high", r"\bPIVOT\b", "PIVOT"),
    SqlPattern("UNPIVOT", "analytics", "high", r"\bUNPIVOT\b", "UNPIVOT"),
    SqlPattern("LATERAL_VIEW", "semi_structured", "high", r"\bLATERAL\s+VIEW\b", "LATERAL VIEW"),
    SqlPattern("EXPLODE", "semi_structured", "high", r"\bEXPLODE\s*\(", "explode()"),
    SqlPattern("JSON_PARSE", "semi_structured", "high", r"\b(?:FROM_JSON|TO_JSON|GET_JSON_OBJECT|JSON_\w+)\b", "JSON functions"),
    SqlPattern("ARRAY_STRUCT", "semi_structured", "medium", r"\b(?:ARRAY|STRUCT)\s*\(", "ARRAY/STRUCT literals"),
    SqlPattern("COLLECT_AGG", "aggregation", "medium", r"\bCOLLECT_(?:LIST|SET)\b", "collect_list/set"),
    SqlPattern("SEMI_ANTI_JOIN", "join", "high", r"\bLEFT\s+(?:SEMI|ANTI)\s+JOIN\b", "Semi/anti joins"),
    SqlPattern("EXCEPT_INTERSECT", "set_ops", "medium", r"\b(?:EXCEPT|INTERSECT)\b", "EXCEPT/INTERSECT"),
    SqlPattern("FULL_OUTER_JOIN", "join", "medium", r"\bFULL\s+(?:OUTER\s+)?JOIN\b", "Full outer join"),
    SqlPattern("CROSS_JOIN", "join", "medium", r"\bCROSS\s+JOIN\b", "Cross join"),
    SqlPattern("TRY_CAST", "type", "medium", r"\bTRY_(?:CAST|TO_\w+)\b", "TRY_CAST / TRY_TO_*"),
    SqlPattern("OPTIMIZE", "delta", "medium", r"\bOPTIMIZE\b", "OPTIMIZE table"),
    SqlPattern("GENERATE_SERIES", "generator", "medium", r"\bGENERATE_SERIES\b", "generate_series()"),
    SqlPattern("UNION_ALL", "set_ops", "medium", r"\bUNION\s+ALL\b", "UNION ALL"),
    SqlPattern("GROUPING_SETS", "aggregation", "medium", r"\b(?:GROUPING\s+SETS|CUBE|ROLLUP)\s*\(", "Grouping sets"),
)

# Known SQL/Databricks functions — matched explicitly so temp views / CTE aliases are excluded.
KNOWN_SQL_FUNCTIONS: frozenset[str] = frozenset(
    {
        "avg", "count", "max", "min", "sum", "stddev", "stddev_pop", "stddev_samp",
        "variance", "var_pop", "var_samp", "collect_list", "collect_set", "first", "last",
        "approx_count_distinct", "approx_percentile", "percentile", "percentile_approx",
        "corr", "covar_pop", "covar_samp", "any_value", "bool_and", "bool_or",
        "row_number", "rank", "dense_rank", "ntile", "lead", "lag", "first_value",
        "last_value", "cume_dist", "percent_rank",
        "concat", "concat_ws", "substring", "substr", "trim", "ltrim", "rtrim", "upper",
        "lower", "initcap", "length", "len", "replace", "regexp_replace", "regexp_extract",
        "split", "instr", "locate", "format_string", "printf", "translate",
        "levenshtein", "base64", "unbase64", "encode", "decode", "hex", "unhex", "lpad", "rpad",
        "repeat", "reverse", "space",
        "abs", "ceil", "ceiling", "floor", "round", "bround", "sqrt", "power", "pow",
        "exp", "log", "log10", "log2", "ln", "sign", "pmod", "rand", "randn",
        "current_date", "current_timestamp", "current_timezone", "now", "date_add",
        "date_sub", "date_diff", "datediff", "date_format", "date_trunc", "date_part",
        "day", "dayofmonth", "dayofweek", "dayofyear", "hour", "minute", "second",
        "month", "year", "quarter", "weekofyear", "weekday", "last_day", "next_day",
        "add_months", "months_between", "from_unixtime", "unix_timestamp", "to_date",
        "to_timestamp", "make_date", "make_timestamp", "make_interval",
        "convert_timezone", "from_utc_timestamp", "to_utc_timestamp",
        "coalesce", "nvl", "nvl2", "if", "ifnull", "nullif", "greatest", "least",
        "cast", "try_cast", "try_to_binary", "try_to_number", "try_to_timestamp",
        "try_to_date", "try_element_at", "isnull", "isnan", "isnotnull",
        "array", "array_contains", "array_distinct", "array_except", "array_intersect",
        "array_join", "array_max", "array_min", "array_position", "array_remove",
        "array_repeat", "array_sort", "array_union", "arrays_overlap", "arrays_zip",
        "flatten", "sequence", "shuffle", "slice", "sort_array", "element_at",
        "explode", "explode_outer", "posexplode", "posexplode_outer", "inline", "inline_outer",
        "map", "map_concat", "map_entries", "map_filter", "map_from_arrays",
        "map_from_entries", "map_keys", "map_values", "struct", "named_struct",
        "from_json", "to_json", "get_json_object", "json_tuple", "schema_of_json", "parse_url",
        "md5", "sha", "sha1", "sha2", "crc32", "hash", "xxhash64", "uuid",
        "monotonically_increasing_id", "spark_partition_id", "input_file_name",
        "optimize", "vacuum", "generate_series", "stack",
    }
)

FUNCTION_CALL_REGEX = re.compile(
    r"\b([a-z][a-z0-9_]*)\s*\(",
    re.IGNORECASE,
)


def compile_patterns() -> dict[str, re.Pattern[str]]:
    return {p.name: re.compile(p.regex, re.IGNORECASE) for p in SQL_PATTERNS}


def extract_functions(sql_text: str) -> set[str]:
    """Return known SQL/Databricks function names used in SQL (lowercase)."""
    found: set[str] = set()
    for match in FUNCTION_CALL_REGEX.finditer(sql_text):
        name = match.group(1).lower()
        if name in KNOWN_SQL_FUNCTIONS:
            found.add(name)
    return found