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

# parse fts file to create dictionary of schema
import re

def read_fts(fts_file):
    """
    Reads a .fts file and extracts column metadata into a structured dictionary.
    """
    with open(fts_file, 'r', encoding='utf-8') as f:
        lines = [line.rstrip() for line in f]

    # Locate the delimiter line (----) and extract header info
    for i, line in enumerate(lines):
        if '----' in line:
            headers = [' '.join(l[start:start+len(match.group())].strip() 
                                for l in lines[i-3:i]).strip()
                       for start, match in zip([0] + [m.end() + 1 for m in re.finditer(r'-+', line[:-1])], 
                                               re.finditer(r'-+', line))]
            break
    else:
        raise ValueError("Invalid .fts file format: No delimiter line found.")

    data_dict = {header: [] for header in headers}

    # Process data rows
    for line in lines[i+1:]:
        if not line or "Note:" in line:
            break
        values = [line[start:start+width].strip() 
                  for start, width in zip([0] + [m.end() + 1 for m in re.finditer(r'-+', lines[i])], 
                                          [len(m.group()) for m in re.finditer(r'-+', lines[i])])]
        for header, value in zip(headers, values):
            data_dict[header].append(value)

    return data_dict

def change_dftypes_pyarrow(data, type_dict, verbose=False):
    """
    Converts column data types based on provided type mapping using PyArrow.
    """
    for col, values in data.items():
        dtype = type_dict.get(col, "CHAR")
        
        if dtype == 'NUM':
            if verbose: print(f"{col}: CHAR --> NUM")
            data[col] = pa.array([float(v) if v.replace('.', '', 1).isdigit() else None for v in values], type=pa.float64())
        
        elif dtype == 'DATE':
            if verbose: print(f"{col}: CHAR --> DATE")
            data[col] = pa.array([datetime.strptime(v, "%Y%m%d") if v else None for v in values], type=pa.date64())
        
        else:  # Default to string (CHAR)
            data[col] = pa.array([v.strip() if v.strip() else None for v in values], type=pa.string())
            if verbose: print(f"{col}: CHAR")
    
    return data

### editing function to run slurm job

def process_dat_struct(dat_file, output_csv, parquet=False, start_row=0, num_rows=100000, verbose=False):
    """
    Parses a .dat file in chunks using struct to unpack fixed-width columns, converts data types, and saves as CSV or Parquet.
    """
    start_time = time.time()
    
    data_dict = read_fts(dat_file.replace('.dat','.fts'))
    keys = list(data_dict.keys())
    headers = data_dict[keys[2]]  # Extract headers from the 3rd key
    column_widths = list(map(int, data_dict[keys[5]]))  # Extract column widths from the 6th key
    data_types = dict(zip(headers, data_dict[keys[3]]))  # Extract data types into a dictionary
    
    # Precompute format string for struct
    format_string = ''.join([f'{width}s' for width in column_widths])  # Fixed-width string unpacking
    
    # Initialize storage for columns
    data = {header: [] for header in headers}
    
    # Read and parse .dat file line by line
    with open(dat_file, 'rb') as f:
        # Skip to start_row
        for _ in range(start_row):
            f.readline()

        for line in islice(f, num_rows):
            unpacked = struct.unpack(format_string, line[:sum(column_widths)])  
            for col_idx, (header, value) in enumerate(zip(headers, unpacked)):
                data[header].append(value.decode('utf-8').strip())

    # Apply type casting
    data = change_dftypes_pyarrow(data, data_types, verbose=verbose)

    # Convert to PyArrow table
    table = pa.table(data)

    # Write CSV
    chunk_output_csv = output_csv.replace('.csv', f'_part_{start_row}.csv')
    pc.write_csv(table, chunk_output_csv)

    # Write Parquet if required
    if parquet:
        pq.write_table(table, chunk_output_csv.replace('.csv', '.parquet'))

    # End measuring time
    end_time = time.time()
    print(f"Chunk {start_row} - {start_row + num_rows} processed in {end_time - start_time:.4f} seconds")

    return table

def main():
    """
    Main function to process the .dat file based on command-line arguments.
    """
    parser = argparse.ArgumentParser(description="Process .dat files into CSV or Parquet.")
    parser.add_argument("dat_file", type=str, help="Path to the .dat file")
    parser.add_argument("output_csv", type=str, help="Path to the output CSV file")
    parser.add_argument("start_row", type=int, help="Starting row for processing")
    parser.add_argument("chunk_size", type=int, help="Number of rows to process in this chunk")
    parser.add_argument("--parquet", action="store_true", help="Whether to also write Parquet files")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")

    args = parser.parse_args()

    # Call the processing function
    process_dat_struct(
        dat_file=args.dat_file,
        output_csv=args.output_csv,
        parquet=args.parquet,
        start_row=args.start_row,
        num_rows=args.chunk_size,
        verbose=args.verbose
    )

if __name__ == "__main__":
    main()



