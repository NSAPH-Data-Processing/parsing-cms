import os
import re
import struct
import time
from itertools import islice
from typing import Optional

import pyarrow as pa

from .fts import read_fts_table, extract_fixedwidth_schema_from_fts_table
from .parquetio import cast_columns_from_fts, write_parquet
from .paths import dat_bucket_parts, ensure_output_dir


def fts_for_dat(dat_file: str) -> str:
    """Return corresponding .fts file for a .dat file, handling _001 suffixes."""
    return re.sub(r"(_\d{3})?\.dat$", ".fts", dat_file)


def read_fixedwidth_chunk(
    dat_file: str,
    headers: list[str],
    widths: list[int],
    start_row: int,
    num_rows: int,
) -> Optional[dict]:
    """
    Read a fixed-width DAT file chunk into dict[str, list[str]].
    """
    # If last width is 0 (unknown), we can still unpack by using the line length.
    # But struct needs explicit widths; so if any width is 0, fallback to slicing logic.
    if any(w == 0 for w in widths):
        return _read_fixedwidth_chunk_by_slicing(dat_file, headers, widths, start_row, num_rows)

    fmt = "".join(f"{w}s" for w in widths)
    row_bytes = sum(widths)

    data = {h: [] for h in headers}

    with open(dat_file, "rb") as f:
        for _ in range(start_row):
            if not f.readline():
                return None

        for line in islice(f, num_rows):
            unpacked = struct.unpack(fmt, line[:row_bytes])
            for h, v in zip(headers, unpacked):
                data[h].append(v.decode("utf-8", errors="ignore").strip())

    return data


def _read_fixedwidth_chunk_by_slicing(
    dat_file: str,
    headers: list[str],
    widths: list[int],
    start_row: int,
    num_rows: int,
) -> Optional[dict]:
    """
    Fallback reader if an FTS width is missing/0.
    We slice using cumulative widths, and for the last 0-width field we take the remainder.
    """
    data = {h: [] for h in headers}
    cum = []
    total = 0
    for w in widths[:-1]:
        total += max(w, 0)
        cum.append(total)

    with open(dat_file, "rb") as f:
        for _ in range(start_row):
            if not f.readline():
                return None

        for line in islice(f, num_rows):
            line_str = line.decode("utf-8", errors="ignore")
            start = 0
            # all but last
            for h, end in zip(headers[:-1], cum):
                data[h].append(line_str[start:end].strip())
                start = end
            # last
            data[headers[-1]].append(line_str[start:].strip())

    return data


def dat_to_parquet_chunk(
    dat_file: str,
    out_root: str,
    start_row: int = 0,
    num_rows: int = 10**6,
    dir_structure: str = "year/file_stem",
    verbose: bool = False,
) -> Optional[str]:
    """
    Process a .dat file chunk and write parquet part file.
    Returns output parquet file path, or None if start_row beyond EOF.
    """
    t0 = time.time()

    fts_file = fts_for_dat(dat_file)
    fts_table = read_fts_table(fts_file)
    headers, widths, _starts, type_map = extract_fixedwidth_schema_from_fts_table(fts_table)

    raw = read_fixedwidth_chunk(dat_file, headers, widths, start_row, num_rows)
    if raw is None:
        return None

    cols = cast_columns_from_fts(raw, type_map, verbose=verbose)
    table = pa.table(cols)

    year, file_stem = dat_bucket_parts(dat_file)
    out_dir = ensure_output_dir(out_root, year, file_stem, dir_structure)

    part = start_row // num_rows + 1
    out_file = os.path.join(out_dir, f"part-{part:02d}.parquet")
    write_parquet(table, out_file)

    print(f"Saved {out_file} ({start_row}..{start_row + num_rows}) in {time.time() - t0:.2f}s")
    return out_file
