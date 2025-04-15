import pyarrow as pa
import pyarrow.parquet as pq
import pyreadstat
from itertools import islice
from datetime import date, datetime
import time
import argparse
import os
import re
import numpy

def create_datapath(sas_file,out_path):
    """Creates a directory for storing processed files."""
    file_name = os.path.basename(sas_file)
    file_stem, _ = os.path.splitext(file_name)  
    match = re.search(r'(\d{4})', file_stem)
    year = match.group(1) if match else file_name # if regex fails, we will still be able to identify the year/file name
    dataset_name = file_stem.replace(year, '').rstrip('_').rstrip('-')  # Remove trailing underscores/hyphens
    output_dir = os.path.join(out_path, year, dataset_name)
    os.makedirs(output_dir, exist_ok=True) 
    
    return output_dir

def change_dtypes(data, verbose=False):
    """Converts column data types based on provided type mapping using PyArrow."""
    for col, values in data.items():
        # Filter out None and NaN values for type detection
        sample_values = [v for v in values if v is not None and not (isinstance(v, float) and numpy.isnan(v))][:10]
        detected_types = set(type(v) for v in sample_values)

        if verbose:
            print(f"Column: {col} | Detected Types: {detected_types}")

        if detected_types <= {date, datetime}:
            if verbose:
                print(f"{col}: Detected date/datetime, converting to PyArrow date64")
            # Replace NaN with None
            cleaned_values = [v if isinstance(v, (date, datetime)) else None for v in values]
            data[col] = pa.array(cleaned_values, type=pa.date64())

        elif detected_types <= {int, float, numpy.float64}:
            if verbose:
                print(f"{col}: Detected numeric, converting to PyArrow float64")
            data[col] = pa.array(
                [float(v) if isinstance(v, (int, float)) and not (isinstance(v, float) and numpy.isnan(v)) else None for v in values],
                type=pa.float64()
            )

        else:
            if verbose:
                print(f"{col}: Detected as string")
            data[col] = pa.array(
                [v.strip() if isinstance(v, str) and v.strip() else None for v in values],
                type=pa.string()
            )
    return data

def process_sas(sas_file, out_path, start_row = 0, num_rows = 10**6, verbose=False):
    """
    Process a SAS file column-wise and save it as Parquet without using pandas.
    """
    start_time = time.time()

    # Read the .sas7bdat file as dictionary instead of default pandas df
    data, meta = pyreadstat.read_sas7bdat(sas_file, row_offset=start_row, row_limit=num_rows,encoding='latin1', output_format='dict')  
    
    # headers = meta.column_names  # Get column names
    # column_types = meta.readstat_variable_types  # Get column types (for type casting)

    # cast datatypes and store as pyarrow arrays
    data = change_dtypes(data, verbose=verbose)
    # convert to pyarrow table
    table = pa.table(data)
    # write to parquet
    output_dir = create_datapath(sas_file, out_path)
    output_file = os.path.join(output_dir, f"part-{start_row // num_rows + 1:02d}.parquet")
    pq.write_table(table, output_file)
    
    end_time = time.time()
    runtime = end_time - start_time
    print(f"Total runtime: {runtime:.4f} seconds")
    
    return table

def main():
    """
    Main function to parse arguments and process the SAS file.
    """
    parser = argparse.ArgumentParser(description="Process SAS files into Parquet.")
    parser.add_argument("sas_file", type=str, help="Path to the SAS file (.sas7bdat)")
    parser.add_argument("out_path", type=str, help="Path to the output Parquet file")
    parser.add_argument("start_row", type=int, help="Starting row for processing")
    parser.add_argument("chunk_size", type=int, help="Number of rows to process in this chunk")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")

    args = parser.parse_args()

    # Call the processing function
    process_sas(
        sas_file=args.sas_file,
        out_path=args.out_path,
        start_row=args.start_row,
        num_rows=args.chunk_size,
        verbose=args.verbose
    )

if __name__ == "__main__":
    main()
