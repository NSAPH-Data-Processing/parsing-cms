import os
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pyarrow.csv as pc
import csv
import re
import sys
import numpy as np
import pyreadstat
from itertools import islice
from datetime import datetime
import time
import struct
import argparse

def process_sas(sas_file, output_csv, parquet=True, verbose=False):
    """
    Process a SAS file column-wise and save it as CSV or Parquet without using pandas.
    """
    start_time = time.time()
    # Read the .sas7bdat file as dictionary instead of default pandas df
    data, meta = pyreadstat.read_sas7bdat(sas_file, output_format='dict')  
    
    headers = meta.column_names  # Get column names
    column_types = meta.readstat_variable_types  # Get column types (for type casting)

    # Convert column-wise
    for col, dtype in column_types.items():
        values = data[col]  # Extract column values
        
        if col == 'DOB': 
            data[col] = pa.array(
                [datetime.strptime(str(int(v)), "%Y%m%d") if v else None for v in values], 
                type=pa.date64()
            )
            if verbose: print(f"{col}: Converted SAS numeric date to PyArrow date64")
            
        elif dtype == 'double':
            if verbose: print(f"{col}: double --> float")
            data[col] = pa.array(values, type=pa.float64())
        
        else:  # Default to string (CHAR)
            data[col] = pa.array(values, type=pa.string())
            if verbose: print(f"{col}: CHAR")
    
    # Convert to PyArrow table
    table = pa.table(data)
    
    # Write CSV
    pc.write_csv(table, output_csv)
    
    # Write Parquet if required
    if parquet:
        pq.write_table(table, output_csv.replace(".csv", ".parquet"))
    
    end_time = time.time()
    runtime = end_time - start_time
    print(f"Total runtime: {runtime:.4f} seconds")
    
    return table

def main():
    """
    Main function to parse arguments and process the SAS file.
    """
    parser = argparse.ArgumentParser(description="Process SAS files into CSV or Parquet.")
    parser.add_argument("sas_file", type=str, help="Path to the SAS file (.sas7bdat)")
    parser.add_argument("output_csv", type=str, help="Path to the output CSV file")
    parser.add_argument("--parquet", action="store_true", help="Whether to also write Parquet files")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")

    args = parser.parse_args()

    # Call the processing function
    process_sas(
        sas_file=args.sas_file,
        output_csv=args.output_csv,
        parquet=args.parquet,
        verbose=args.verbose
    )

if __name__ == "__main__":
    main()
