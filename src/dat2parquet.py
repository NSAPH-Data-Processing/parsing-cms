import pyarrow as pa
import pyarrow.parquet as pq
import re
import os
import struct
import time
import argparse
from itertools import islice
from datetime import datetime

def read_fts(fts_file):
    """Reads a .fts file and extracts column metadata into a structured dictionary."""
    if not os.path.exists(fts_file):
        raise FileNotFoundError(f"FTS file not found: {fts_file}")

    with open(fts_file, 'r', encoding='utf-8') as f:
        lines = [line.rstrip() for line in f]

    for i, line in enumerate(lines):
        if '----' in line: # this line marks the begininng of the table, and the # of -'s provides column width
            #format stacked headers into one line
            headers = [' '.join(l[start:start+len(match.group())].strip() 
                                for l in lines[i-3:i]).strip()
                       for start, match in zip([0] + [m.end() + 1 for m in re.finditer(r'-+', line[:-1])], 
                                               re.finditer(r'-+', line))]
            break
    else:
        raise ValueError("Invalid .fts file format: No delimiter line found.")
    # initialize dictionary to store schema
    data_dict = {header: [] for header in headers}
    # extract information rowwise
    for line in lines[i+1:]:
        if not line or "Note:" in line:
            break
        values = [line[start:start+width].strip() 
                  for start, width in zip([0] + [m.end() + 1 for m in re.finditer(r'-+', lines[i])], 
                                          [len(m.group()) for m in re.finditer(r'-+', lines[i])])]
        for header, value in zip(headers, values):
            data_dict[header].append(value)

    return data_dict

def change_dtypes(data, type_dict, verbose=False):
    """Converts column data types based on provided type mapping using PyArrow."""
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

def create_datapath(dat_file,out_path):
    """Creates a directory for storing processed files."""
    file_name = os.path.basename(dat_file)
    match = re.search(r'_(\d{4})(?:_\d+|\.|$)', file_name) # Extracts the year from the filename, handling different naming conventions
    year = match.group(1) if match else file_name
    file_stem = file_name.rsplit("_", 1)[0]  
    output_dir = os.path.join(out_path, year, file_stem)
    os.makedirs(output_dir, exist_ok=True)

    return output_dir

def process_dat(dat_file, out_path, start_row=0, num_rows=10**6, verbose=False):
    """Processes a .dat file in chunks, extracts data using struct, and saves as Parquet."""
    start_time = time.time()

    # processing file name for fts identification if file has multiple parts
    base_name = re.sub(r'_\d{3}\.dat$', '', dat_file)  # Remove _001, _002, etc., from the .dat file name
    fts_file = base_name.replace('.dat', '.fts')
    data_dict = read_fts(fts_file)
    keys = list(data_dict.keys())

    if len(keys) < 6:  
        raise ValueError("FTS file does not contain expected metadata fields.")

    headers = data_dict[keys[2]]
    column_widths_raw = data_dict[keys[5]]
    start_columns = list(map(int, data_dict[keys[4]]))
    data_types = dict(zip(headers, data_dict[keys[3]]))

    # calculate column width using col start from fts file if typo exists in field width column
    column_widths = [
        int(width) if width.isdigit() else (start_columns[i + 1] - start_columns[i])
        for i, width in enumerate(column_widths_raw[:-1])
    ]
    # handle the last column width
    column_widths.append(int(column_widths_raw[-1]) if column_widths_raw[-1].isdigit() else None)
    
    # set format of widths for byte parsing
    format_string = ''.join([f'{width}s' for width in column_widths])

    data = {header: [] for header in headers}
    # read file in bytes
    with open(dat_file, 'rb') as f:
        for _ in range(start_row):
            if not f.readline():
                print(f"Warning: start_row ({start_row}) exceeds file size.")
                return None
        # read chunk
        for line in islice(f, num_rows):
            # parse each line according to the format string
            unpacked = struct.unpack(format_string, line[:sum(column_widths)])  
            for header, value in zip(headers, unpacked):
                # decode bytes and strip whitespace
                data[header].append(value.decode('utf-8').strip()) 

    # cast datatypes to be compatible with parquet and store cols as pyarrow array
    data = change_dtypes(data, data_types, verbose=verbose)
    # create pyarrow table
    table = pa.table(data)
    # write to parquet
    output_dir = create_datapath(dat_file, out_path)
    output_file = os.path.join(output_dir, f"part-{start_row // num_rows + 1:02d}.parquet")
    pq.write_table(table, output_file)

    print(f"Chunk {start_row} - {start_row + num_rows} saved to {output_file} in {time.time() - start_time:.4f} seconds")
    
    return output_file

def main():
    parser = argparse.ArgumentParser(description="Process .dat files into Parquet.")
    parser.add_argument("dat_file", type=str, help="Path to the .dat file")
    parser.add_argument("out_path", type=str, help="Base path to the output directory")
    parser.add_argument("start_row", type=int, help="Starting row for processing")
    parser.add_argument("chunk_size", type=int, help="Number of rows to process in this chunk")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")

    args = parser.parse_args()

    process_dat(
        dat_file=args.dat_file,
        out_path=args.out_path,
        start_row=args.start_row,
        num_rows=args.chunk_size,
        verbose=args.verbose
    )

if __name__ == "__main__":
    main()




