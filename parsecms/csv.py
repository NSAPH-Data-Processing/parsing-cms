import os
import re
import time
import pyarrow as pa
import pyarrow.csv as pv

from .fts import fts_schema
from .parquetio import cast_columns_from_fts, write_parquet
from .paths import csv_bucket_parts, ensure_output_dir


def fts_for_csv(csv_file: str) -> str:
    """
    map csv to fts:
      maxdata_co_ip_2011.csv -> maxdata_co_ip_2011.fts
    """
    base = os.path.basename(csv_file)
    fts_name = re.sub(r"_(?:[a-z]{2})_", "_", base)
    return os.path.join(os.path.dirname(csv_file), os.path.splitext(fts_name)[0] + ".fts")


def csv_to_parquet(
    csv_file: str,
    out_root: str,
    dir_structure: str = "year/file_stem",
    verbose: bool = False,
) -> str:
    t0 = time.time()

    fts_file = fts_for_csv(csv_file)
    type_map = fts_schema(fts_file, col_field="Column", type_field="SAS Type")
    headers = list(type_map.keys())

    read_options = pv.ReadOptions(column_names=headers, use_threads=True)
    convert_options = pv.ConvertOptions(column_types={h: pa.string() for h in headers})
    table = pv.read_csv(csv_file, read_options=read_options, convert_options=convert_options)

    data = {col: table[col].to_pylist() for col in headers}
    cols = cast_columns_from_fts(data, type_map, verbose=verbose)
    out_table = pa.table(cols)

    year, file_stem = csv_bucket_parts(csv_file)
    out_dir = ensure_output_dir(out_root, year, file_stem, dir_structure)

    out_file = os.path.join(out_dir, "part-01.parquet")
    write_parquet(out_table, out_file)

    print(f"Saved {out_table.num_rows} rows to {out_file} in {time.time() - t0:.2f}s")
    return out_file
