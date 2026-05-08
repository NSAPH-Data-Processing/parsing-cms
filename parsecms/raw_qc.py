import argparse
import json
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Any

import duckdb

from parsecms.fts import read_fts_table

# -----------------------------
# Helpers: MAX CSV FTS expected rows
# -----------------------------
def expected_rows_from_max_csv_fts(fts_file: str, csv_input_file: str) -> Optional[int]:
    """
    MAX CSV-style FTS contains many lines like:

      Data File: maxdata_ak_ip_2007.csv  Rows:     20,311  Size(Bytes): ...

    We match the basename of the input CSV and extract the Rows count.
    """
    csv_base = Path(csv_input_file).name
    if not os.path.exists(fts_file):
        return None

    with open(fts_file, "r", encoding="utf-8") as f:
        for line in f:
            if "Data File:" in line and csv_base in line and "Rows:" in line:
                m = re.search(r"Rows:\s*([\d,]+)", line)
                if m:
                    return int(m.group(1).replace(",", ""))
    return None


# -----------------------------
# Helpers: expected shape from FTS *text*
# -----------------------------
def expected_shape_from_fts_text(fts_file: str, source_input: Optional[str] = None) -> Dict[str, Optional[int]]:
    """
    Extract expected rows/columns from FTS *text*, if present.
    Supports:
      - DAT-like FTS (base_name (N Rows), Columns in File, Exact File Quantity)
      - MAX CSV FTS (Data File: <csv> Rows: N)

    Returns: {"rows": int|None, "columns": int|None}
    """
    expected = {"rows": None, "columns": None}

    if not os.path.exists(fts_file):
        return expected

    base_name = Path(fts_file).stem

    with open(fts_file, "r", encoding="utf-8") as f:
        lines = f.readlines()

    for line in lines:
        if "Columns in File" in line:
            m = re.search(r"Columns in File:\s*(\d+)", line)
            if m:
                expected["columns"] = int(m.group(1))
                break

    # Rows patterns vary; try a few 
    for line in lines:
        if base_name in line:
            m = re.search(r"\(([\d,]+)\s+Rows\)", line)
            if m:
                expected["rows"] = int(m.group(1).replace(",", ""))
                break
    if expected["rows"] is None:
        for line in lines:
            if "Exact File Quantity (Rows)" in line:
                m = re.search(r"Exact File Quantity \(Rows\):\s*([\d,]+)", line)
                if m:
                    expected["rows"] = int(m.group(1).replace(",", ""))
                    break

    if expected["rows"] is None and source_input:
        if Path(source_input).suffix.lower() == ".csv":
            r = expected_rows_from_max_csv_fts(fts_file, source_input)
            if r is not None:
                expected["rows"] = r

    return expected


# -----------------------------
# Helpers: expected column names from FTS table
# -----------------------------
def pick_expected_column_field(fts_table: Dict[str, List[str]]) -> Optional[str]:
    """
    Choose which FTS metadata column contains the dataset column names.

    Different FTS variants might call this:
      - "Field Short Name"
      - "Field Name"
      - "Column"
      - "Field"
    """
    keys = list(fts_table.keys())
    norm = lambda s: re.sub(r"[^a-z]+", " ", str(s).lower()).strip()

    candidates = [
        "field short name",
        "field name",
        "column",
        "field",
    ]
    norm_keys = {norm(k): k for k in keys}

    for c in candidates:
        for nk, orig in norm_keys.items():
            if c == nk:
                return orig

    for nk, orig in norm_keys.items():
        if "short" in nk and "name" in nk:
            return orig
    for nk, orig in norm_keys.items():
        if "field" in nk and "name" in nk:
            return orig
    for nk, orig in norm_keys.items():
        if "column" in nk:
            return orig

    return None


def expected_columns_from_fts(fts_file: str) -> Optional[List[str]]:
    """
    Return expected dataset column names (as listed in the FTS table) if possible.
    Otherwise return None.
    """
    if not fts_file or not os.path.exists(fts_file):
        return None

    fts_table = read_fts_table(fts_file)
    col_field = pick_expected_column_field(fts_table)
    if col_field is None:
        return None

    cols = []
    for c in fts_table.get(col_field, []):
        c = (c or "").strip()
        if c:
            cols.append(c)
    return cols or None


# -----------------------------
# DuckDB QC core
# -----------------------------
def run_duckdb_qc_on_parquet_dir(
    parquet_dir: str,
    fts_file: Optional[str] = None,
    qc_output: Optional[str] = None,
    source_input: Optional[str] = None,  # NEW: original .dat/.csv/.sas input path
) -> Dict[str, Any]:
    """
    Run QC over all parquet files in parquet_dir (part-*.parquet).
    If fts_file is provided and exists, do schema & expected-shape comparisons.
    If not, still produce useful QC metrics.

    `source_input` is used to support MAX CSV FTS row matching (Data File: ... Rows: ...).
    """
    parquet_dir = str(parquet_dir)
    base_path = Path(parquet_dir)

    parquet_glob = str(base_path / "*.parquet")
    con = duckdb.connect()
    con.execute(f"CREATE OR REPLACE VIEW df AS SELECT * FROM '{parquet_glob}'")

    report: Dict[str, Any] = {}

    # ---- Actual shape ----
    actual_rows = con.execute("SELECT COUNT(*) FROM df").fetchone()[0]
    actual_cols = len(con.execute("PRAGMA table_info('df')").fetchall())
    shape_report: Dict[str, Any] = {
        "actual_rows": int(actual_rows),
        "actual_columns": int(actual_cols),
    }

    # ---- Expected shape (FTS text) ----
    exp_cols_list: Optional[List[str]] = None

    if fts_file and os.path.exists(fts_file):
        expected_shape = expected_shape_from_fts_text(fts_file, source_input=source_input)

        # Expected columns list (from FTS table) — also used as fallback for expected_columns count
        exp_cols_list = expected_columns_from_fts(fts_file)

        if expected_shape.get("rows") is not None:
            shape_report["expected_rows"] = expected_shape["rows"]
            shape_report["row_mismatch"] = (actual_rows != expected_shape["rows"])

        # Columns: prefer explicit "Columns in File", else fallback to schema length
        exp_cols_count = expected_shape.get("columns")
        if exp_cols_count is None and exp_cols_list:
            exp_cols_count = len(exp_cols_list)

        if exp_cols_count is not None:
            shape_report["expected_columns"] = exp_cols_count
            shape_report["column_mismatch"] = (actual_cols != exp_cols_count)

    report["shape_check"] = shape_report

    # ---- Column list ----
    actual_columns = [row[1] for row in con.execute("PRAGMA table_info('df')").fetchall()]
    report["actual_columns"] = actual_columns

    # ---- Expected columns (schema) ----
    exp_cols = exp_cols_list
    if exp_cols:
        exp_cols_norm = [c.strip() for c in exp_cols]
        missing_columns = [c for c in exp_cols_norm if c not in actual_columns]
        unexpected_columns = [c for c in actual_columns if c not in exp_cols_norm]
        report["expected_columns"] = exp_cols_norm
        report["missing_columns"] = missing_columns
        report["unexpected_columns"] = unexpected_columns
        report["fts_used_for_schema"] = True
    else:
        report["expected_columns"] = None
        report["missing_columns"] = None
        report["unexpected_columns"] = None
        report["fts_used_for_schema"] = False

    # ---- Column checks: null counts + distinct counts ----
    column_checks: Dict[str, Any] = {}
    for col in actual_columns:
        col_report: Dict[str, Any] = {}
        qcol = f'"{col}"'
        col_report["missing_values"] = int(con.execute(f"SELECT COUNT(*) FROM df WHERE {qcol} IS NULL").fetchone()[0])
        col_report["unique_values"] = int(con.execute(f"SELECT COUNT(DISTINCT {qcol}) FROM df").fetchone()[0])
        column_checks[col] = col_report
    report["column_checks"] = column_checks

    # ---- Duplicates ----
    try:
        column_list = ", ".join([f'"{c}"' for c in actual_columns])
        query = f"""
            SELECT COALESCE(SUM(dupe), 0) AS duplicate_count
            FROM (
                SELECT (COUNT(*) - 1) AS dupe
                FROM df
                GROUP BY {column_list}
                HAVING COUNT(*) > 1
            )
        """
        dupe_count = con.execute(query).fetchone()[0]
        report["duplicate_rows"] = int(dupe_count) if dupe_count is not None else 0
    except Exception as e:
        report["duplicate_rows"] = f"Error checking duplicates: {e}"

    # ---- Numeric summary ----
    numeric_cols = con.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'df' AND data_type IN ('INTEGER', 'BIGINT', 'DOUBLE', 'FLOAT', 'DECIMAL')
    """).fetchall()

    numeric_summary: Dict[str, Any] = {}
    for col in [r[0] for r in numeric_cols]:
        qcol = f'"{col}"'
        try:
            stats = con.execute(f"""
                SELECT
                    MIN({qcol}),
                    MAX({qcol}),
                    AVG({qcol}),
                    CASE WHEN COUNT({qcol}) > 1 THEN STDDEV_POP({qcol}) ELSE NULL END
                FROM df
            """).fetchone()
            numeric_summary[col] = {"min": stats[0], "max": stats[1], "mean": stats[2], "stddev": stats[3]}
        except Exception as e:
            numeric_summary[col] = {"error": f"Could not summarize {col}: {e}"}
    report["numeric_summary"] = numeric_summary

    # ---- Top categories for strings ----
    string_cols = con.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'df' AND data_type IN ('VARCHAR', 'TEXT')
    """).fetchall()

    top_categories: Dict[str, Any] = {}
    for col in [r[0] for r in string_cols]:
        qcol = f'"{col}"'
        try:
            counts = con.execute(
                f"SELECT {qcol}, COUNT(*) AS n FROM df GROUP BY {qcol} ORDER BY n DESC LIMIT 5"
            ).fetchall()
            top_categories[col] = {val: int(cnt) for val, cnt in counts if val is not None}
        except Exception as e:
            top_categories[col] = {"error": str(e)}
    report["top_categories"] = top_categories

    # ---- Save report ----
    if qc_output:
        out_path = Path(qc_output)
    else:
        out_path = base_path / "qc_report.json"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2)

    return report


# -----------------------------
# Locate FTS file (optional)
# -----------------------------
def find_fts_for_input(input_file: str) -> Optional[str]:
    """
    Best-effort FTS discovery:
    - If input is .dat: same stem with optional _NNN stripped
    - If input is .csv: collapse state code like maxdata_ak_ip_2004.csv -> maxdata_ip_2004.fts (in same dir)
    """
    p = Path(input_file)
    if not p.exists():
        return None

    ext = p.suffix.lower()

    if ext == ".dat":
        fts = re.sub(r"(_\d{3})?\.dat$", ".fts", str(p))
        return fts if os.path.exists(fts) else None

    if ext == ".csv":
        base = p.name
        fts_name = re.sub(r"_(?:[a-z]{2})_", "_", base, flags=re.IGNORECASE)
        fts_path = p.with_name(Path(fts_name).with_suffix(".fts").name)
        return str(fts_path) if fts_path.exists() else None

    return None


# -----------------------------
# CLI
# -----------------------------
def main():
    parser = argparse.ArgumentParser(description="Run DuckDB QC over a parquet directory (optionally using an FTS).")
    parser.add_argument(
        "--parquet-dir",
        required=True,
        help="Directory containing part-*.parquet",
    )
    parser.add_argument("--fts-file", default=None, help="Optional path to .fts file for expected schema/shape checks")
    parser.add_argument("--qc-output", default=None, help="Optional path to write qc_report.json")
    parser.add_argument("--infer-fts-from-input", default=None, help="Optional: provide original input file to auto-find FTS")

    args = parser.parse_args()

    fts_file = args.fts_file
    if not fts_file and args.infer_fts_from_input:
        fts_file = find_fts_for_input(args.infer_fts_from_input)

    report = run_duckdb_qc_on_parquet_dir(
        parquet_dir=args.parquet_dir,
        fts_file=fts_file,
        qc_output=args.qc_output,
        source_input=args.infer_fts_from_input,  # NEW: pass through for MAX CSV row matching
    )

    print(json.dumps(report.get("shape_check", {}), indent=2))
    if fts_file:
        print(f"[INFO] QC used FTS: {fts_file}")
    else:
        print("[INFO] QC ran without FTS (shape/schema comparisons skipped).")


if __name__ == "__main__":
    main()



