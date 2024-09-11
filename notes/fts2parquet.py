import pandas as pd
import os
import argparse
import math
from typing import List, Tuple, Any, Callable

from dorieh.cms.fts2yaml import mcr_type, MedicareFTS
from dorieh.platform.loader.data_loader import DataLoader
from dorieh.cms.mcr_data_loader import MedicareDataLoader
from dorieh.cms.tools.mcr_fts2db import MedicareLoader
from dorieh.utils.fwf import FWFReader
from dorieh.utils.io_utils import fopen


# takes fts path and converts .dat to parquet
def fts2parquet(fts_path, parquet_path=None, max_rows = None, verbose=True):

    # extracting basic information about file
    f, _ = os.path.splitext(fts_path)
    _, fname = os.path.split(f)
    t = mcr_type(fname)
    dat_path = f + ".dat"

    if max_rows is None:
        max_rows = math.inf
    else:
        max_rows = int(max_rows)

    if parquet_path is None:
        parquet_path = f + ".parquet"

    # initializing fts object
    fts = MedicareFTS(t).init(fts_path)

    # getting column names
    fts_meta = fts.to_fwf_meta(dat_path)
    colnm_lst = [col.name for col in fts_meta.columns]

    # reading body of .dat file, one row at a time
    with FWFReader(fts_meta) as reader:
        # this gives us one row at a time
        dat = []
        record_count = 0 
        for record in reader:
            dat.append(record)
            record_count += 1 
            # optional printing of progress
            if verbose and record_count % 5000000 == 0:
                print(record_count)

            # stop loading data if have reached max rows
            if record_count >= max_rows:
                break
    
        reader.close()

    # turning list into data frame object and exporting to parquet
    print("List --> DataFrame")
    df_out = pd.DataFrame(df_out, columns = colnm_lst)
    df_out.to_parquet(parquet_path)

    return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Takes .fts and .dat files and produces a .parquet file')
    parser.add_argument('fts_path', type=str, help='Name of spaceenv to be used')
    parser.add_argument('--parquet_path', type=str, default=None, help='[optional] parquet path')
    parser.add_argument('--max_rows', type=int, default=None, help='[optional] Maximum number of rows to read in')
    parser.add_argument('--verbose', type=bool, default=True, help='[optional] Log progress of loading .dat file')
    args = parser.parse_args()

    fts2parquet(fts_path=args.fts_path,
                parquet_path=args.parquet_path,
                max_rows = args.max_rows,
                verbose = args.verbose)
