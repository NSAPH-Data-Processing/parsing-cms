import re
from datetime import datetime
from typing import Dict, List, Any
import pyarrow as pa
import pyarrow.parquet as pq


_NUM_RE = re.compile(r"^-?\d+(\.\d+)?$")


def cast_columns_from_fts(data: Dict[str, List[str]], type_map: Dict[str, str], verbose: bool = False) -> Dict[str, pa.Array]:
    """
    Cast string columns based on FTS type_map (NUM/DATE/CHAR).
    Works for both DAT and CSV (after reading as strings).
    """
    out: Dict[str, pa.Array] = {}
    for col, values in data.items():
        dtype = type_map.get(col, "CHAR")

        if dtype == "NUM":
            if verbose:
                print(f"{col}: CHAR -> NUM")
            out[col] = pa.array(
                [float(v) if v and _NUM_RE.match(v.strip()) else None for v in values],
                type=pa.float64(),
            )

        elif dtype == "DATE":
            if verbose:
                print(f"{col}: CHAR -> DATE")
            out[col] = pa.array(
                [datetime.strptime(v.strip(), "%Y%m%d") if v and v.strip() else None for v in values],
                type=pa.date64(),
            )

        else:
            if verbose:
                print(f"{col}: CHAR")
            out[col] = pa.array(
                [v.strip() if v and v.strip() else None for v in values],
                type=pa.string(),
            )

    return out


def write_parquet(table: pa.Table, output_file: str) -> None:
    """
    Central place for parquet write options (compression, row_group_size, etc.).
    """
    pq.write_table(table, output_file)
