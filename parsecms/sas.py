import os
import time

import pyarrow as pa
import pyreadstat

from .paths import sas_bucket_parts, ensure_output_dir
from .parquetio import write_parquet
from .sas_cast import cast_pyreadstat_columns


def sas_to_parquet_chunk(
    sas_file: str,
    out_root: str,
    start_row: int = 0,
    num_rows: int = 10**6,
    dir_structure: str = "year/file_stem",
    verbose: bool = False,
    encoding: str = "latin1",
) -> str:
    t0 = time.time()

    data, _meta = pyreadstat.read_sas7bdat(
        sas_file,
        row_offset=start_row,
        row_limit=num_rows,
        encoding=encoding,
        output_format="dict",
    )

    cols = cast_pyreadstat_columns(data, verbose=verbose)
    table = pa.table(cols)

    year, dataset = sas_bucket_parts(sas_file)
    out_dir = ensure_output_dir(out_root, year, dataset, dir_structure)

    part = start_row // num_rows + 1
    out_file = os.path.join(out_dir, f"part-{part:02d}.parquet")
    write_parquet(table, out_file)

    print(f"Saved {out_file} in {time.time() - t0:.2f}s")
    return out_file
