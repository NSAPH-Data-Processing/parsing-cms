import pyarrow as pa
import pyarrow.parquet as pq
import pyreadstat
from itertools import islice
from datetime import datetime
import time
import argparse
import os
import re

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

def change_dtypes(data, column_types,verbose = False):
    """Converts column data types based on provided type mapping using PyArrow."""
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
    return data

def process_sas(sas_file, out_path, start_row = 0, num_rows = 10**6, verbose=False):
    """
    Process a SAS file column-wise and save it as Parquet without using pandas.
    """
    start_time = time.time()

    # Read the .sas7bdat file as dictionary instead of default pandas df
    data, meta = pyreadstat.read_sas7bdat(sas_file, row_offset=start_row, row_limit=num_rows, output_format='dict')  
    
    # headers = meta.column_names  # Get column names
    column_types = meta.readstat_variable_types  # Get column types (for type casting)

    # cast datatypes and store as pyarrow arrays
    data = change_dtypes(data, column_types, verbose=verbose)
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
