# parsecms/chunkplan.py
import json
import os
from typing import Optional

import pyreadstat

from parsecms.fts import read_fts_table, extract_fixedwidth_schema_from_fts_table
from parsecms.dat import fts_for_dat
from parsecms.raw_qc import expected_shape_from_fts_text


def _dat_row_count(dat_file: str) -> int:
    fts_file = fts_for_dat(dat_file)

    expected = expected_shape_from_fts_text(fts_file)
    if expected.get("rows") is not None:
        return expected["rows"]

    fts_table = read_fts_table(fts_file)
    _, widths, _, _ = extract_fixedwidth_schema_from_fts_table(fts_table)

    record_len = sum(w for w in widths if w and w > 0)
    if record_len <= 0:
        raise ValueError(f"Could not compute record length from FTS: {fts_file}")

    size = os.path.getsize(dat_file)
    return max(0, size // record_len)


def _sas_row_count(sas_file: str, encoding: str = "latin1") -> int:
    # metadataonly is fast; does not load data
    _, meta = pyreadstat.read_sas7bdat(
        sas_file, metadataonly=True, encoding=encoding
    )
    return int(meta.number_rows)


def compute_n_chunks(
    input_file: str,
    parser_type: str,
    chunk_size: Optional[int],
    sas_encoding: str = "latin1",
) -> int:
    if not chunk_size or int(chunk_size) <= 0:
        return 1

    chunk_size = int(chunk_size)

    if parser_type == "dat":
        nrows = _dat_row_count(input_file)
    elif parser_type == "sas":
        nrows = _sas_row_count(input_file, encoding=sas_encoding)
    else:
        # csv handled elsewhere; no chunking
        return 1

    n_chunks = (nrows + chunk_size - 1) // chunk_size
    return max(1, int(n_chunks))


def main():
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--input-file", required=True)
    ap.add_argument("--parser-type", required=True, choices=["dat", "sas"])
    ap.add_argument("--chunk-size", type=int, default=0)
    ap.add_argument("--sas-encoding", default="latin1")
    ap.add_argument("--out-json", required=True)
    args = ap.parse_args()

    n = compute_n_chunks(
        input_file=args.input_file,
        parser_type=args.parser_type,
        chunk_size=args.chunk_size,
        sas_encoding=args.sas_encoding,
    )

    os.makedirs(os.path.dirname(args.out_json), exist_ok=True)
    with open(args.out_json, "w") as f:
        json.dump({"n_chunks": n}, f)

if __name__ == "__main__":
    main()