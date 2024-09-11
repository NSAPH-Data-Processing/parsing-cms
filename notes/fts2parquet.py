import argparse
#import glob
import pandas as pd
import numpy as np
#import datetime
import os
from typing import List, Tuple, Any, Callable
from itertools import accumulate

from dorieh.cms.fts2yaml import mcr_type, MedicareFTS
from dorieh.platform.loader.data_loader import DataLoader
from dorieh.cms.mcr_data_loader import MedicareDataLoader
from dorieh.cms.tools.mcr_fts2db import MedicareLoader
from dorieh.utils.fwf import FWFReader
from dorieh.utils.io_utils import fopen


# fast line parser for fixed-width files
def fwf_parser(fieldwidths):
    # get absolute cut points for columns
    cuts = tuple(cut for cut in accumulate(abs(fw) for fw in fieldwidths))
    # turn into tuples
    flds = tuple(zip((0,)+cuts, cuts))
    # format into string and pass to eval() for lazy evaluation
    slcs = ', '.join(f'line[{i}:{j}]' for i, j in flds)
    parse = eval('lambda line: ({})\n'.format(slcs))  # Create and compile source code.
    return parse

def change_dftypes(df, type_dict, verbose=False):
    for col in df.columns:
        if type_dict[col] == 'NUM':
            if verbose: 
                print(col + ": CHAR --> NUM")
            df[col] = pd.to_numeric(df[col].str.strip(), errors='coerce')
        elif type_dict[col] == 'DATE':
            if verbose: 
                print(col + ": CHAR --> DATE")
            df[col] = pd.to_datetime(df['COVSTART'], errors='coerce')
        else:
            df[col] = df[col].str.strip().replace('', np.nan)
            if verbose: 
                print(col + ": CHAR")
    return(df)

# takes fts path and converts .dat to parquet
def fts2parquet(fts_path, parquet_path=None, max_rows = None, row_step = 10**6, verbose=True):

    # extracting basic information about file
    f, _ = os.path.splitext(fts_path)
    _, fname = os.path.split(f)
    t = mcr_type(fname)
    dat_path = f + ".dat"
    if parquet_path is None:
        parquet_path = f + ".parquet"

    # initializing fts object
    fts = MedicareFTS(t).init(fts_path)

    # getting column names
    fts_meta = fts.to_fwf_meta(dat_path)
    colnm_lst = [col.name for col in fts_meta.columns]
    colwidth_lst = [col.length for col in fts_meta.columns]
    #colspecs = [(col.start, col.end) for col in fts_meta.columns]
    type_dict = {col.name: col.type for col in fts_meta.columns}
    parse = fwf_parser(colwidth_lst)

    # read raw fixed width file
    print("Reading raw fw file " + dat_path + "...")
    with open(dat_path, "r") as f:
        lines = f.read().split("\n")
        f.close()

    if max_rows is not None:
        max_rows = min(max_rows, len(lines))
    else:
        max_rows = len(lines)

    row_min = 0
    row_max = row_step
    parsed_df_lst = []
    while row_min < max_rows:
        if row_max >= max_rows: 
            row_max = max_rows
        print("Processing rows " + str(row_min) + " to " + str(row_max))
        # parsing raw text into columns
        prs_df_tmp = pd.DataFrame([parse(line) for line in lines[row_min:row_max]], 
                                  columns=colnm_lst)
        # modifying data frame types
        parsed_df_lst.append(change_dftypes(prs_df_tmp, type_dict=type_dict, verbose=False))
        row_min = row_max
        row_max += row_step
    
    # concatenating all dataframes
    print("Concatenating data frames")
    full_df = pd.concat(parsed_df_lst)
    
    # printing number of NAs in every columns
    print("NA summary statistics")
    print(full_df.isnull().sum())


    # turning list into data frame object and exporting to parquet
    print("DF --> parquet")
    full_df.to_parquet(parquet_path)

    return None


def main(args):
    pd.set_option('future.no_silent_downcasting', True)
    if args.max_rows is not None:
        max_rows = int(args.max_rows)
    if args.row_step is not None:
        row_step = int(args.row_step)

    fts2parquet(fts_path=args.fts_path,
                parquet_path=args.parquet_path,
                max_rows = max_rows,
                row_step = row_step,
                verbose = args.verbose)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Takes .fts and .dat files and produces a .parquet file')
    parser.add_argument('fts_path', type=str, help='Name of spaceenv to be used')
    parser.add_argument('--parquet_path', type=str, default=None, help='[optional] parquet path')
    parser.add_argument('--row_step', type=int, default=None, help='[optional] Maximum number of rows to read in')
    parser.add_argument('--max_rows', type=int, default=None, help='[optional] Maximum number of rows to read in')
    parser.add_argument('--verbose', type=bool, default=True, help='[optional] Log progress of loading .dat file')
    args = parser.parse_args()

    main(args)


# python3 notes/fts2parquet.py "/n/dominici_nsaph_l3/Lab/data/ci3_d_medicare/original_data/cms_medicare/data/4334/2012/mbsf_ab_summary_res000017155_req004334_2012.fts" \
#    --parquet_path "data/tmp.parquet" --row_step 1000000 --max_rows 10000000 --verbose "False"