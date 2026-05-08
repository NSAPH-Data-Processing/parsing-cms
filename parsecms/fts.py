"""
Robust FTS parsing utilities used by parsecms.{csv,dat}.

Provides:
- read_fts_table(fts_file, max_header_lines=3, verbose=False)
- fts_schema(fts_file, col_field="Column", type_field="SAS Type")
- extract_fixedwidth_schema_from_fts_table(fts_table)
"""
import os
import re
from typing import Dict, List, Tuple


def read_fts_table(fts_file: str, max_header_lines: int = 3, verbose: bool = False) -> Dict[str, List[str]]:
    """
    Parse an FTS into a dict mapping composed header -> list of values for that column.

    Behavior:
    - Finds the dashed delimiter line (----...) that marks the header boundary.
    - Collects the contiguous block of non-empty header lines immediately above the delimiter
      (this handles 2-line CSV FTS headers and 3-line DAT FTS headers).
    - Uses the spans on the delimiter line to slice header pieces and data rows.
    - Returns {header_name: [col_values, ...]}.

    Footer handling:
    - Stops parsing when encountering common footer markers
    """
    if not os.path.exists(fts_file):
        raise FileNotFoundError(f"FTS file not found: {fts_file}")

    with open(fts_file, "r", encoding="utf-8") as f:
        lines = [line.rstrip("\n") for line in f]

    # Find dashed delimiter line
    delim_idx = None
    delim_line = None
    for i, line in enumerate(lines):
        if re.search(r"-{4,}", line):
            delim_idx = i
            delim_line = line
            break
    if delim_idx is None or delim_line is None:
        raise ValueError("Invalid .fts format: No dashed delimiter line found.")

    # compute spans/starts/widths from the delimiter line
    spans = [(m.start(), m.end()) for m in re.finditer(r"-+", delim_line)]
    starts = [0] + [end + 1 for _, end in spans[:-1]]
    widths = [end - start for start, end in spans]

    # Collect contiguous non-empty header lines immediately above the delimiter.
    header_lines: List[str] = []
    j = delim_idx - 1
    while j >= 0 and len(header_lines) < max_header_lines and lines[j].strip():
        header_lines.append(lines[j])
        j -= 1
    header_lines = list(reversed(header_lines))  # now top -> bottom order

    # If we didn't find any header lines (odd case), fall back to up-to-3 non-empty lines above delimiter
    if not header_lines:
        k = delim_idx - 1
        tmp: List[str] = []
        while k >= 0 and len(tmp) < max_header_lines:
            if lines[k].strip():
                tmp.append(lines[k])
            k -= 1
        header_lines = list(reversed(tmp))

    # Build header names by concatenating the header lines for each span
    headers: List[str] = []
    for start, width in zip(starts, widths):
        h_parts: List[str] = []
        for hl in header_lines:
            # safe slice — some header lines might be shorter
            piece = hl[start:start + width].strip() if len(hl) > start else ""
            if piece:
                h_parts.append(piece)
        h = " ".join(h_parts).strip()
        # fallback: use a cleaned slice from the delimiter line if nothing captured
        if not h:
            h = delim_line[start:start + width].strip().strip("-").strip()
        headers.append(h)

    if verbose:
        print("FTS parsing diagnostics:")
        print("  delim_idx:", delim_idx)
        print("  header_lines (top->bottom):")
        for hl in header_lines:
            print("    >", hl)
        print("  num headers:", len(headers))
        print("  starts:", starts)
        print("  widths:", widths)
        print("  headers sample:", headers[:10])

    # Initialize table mapping
    table: Dict[str, List[str]] = {h: [] for h in headers}

    footer_markers = (
        "end of file transfer summary",
        "-- end of file transfer summary",
    )

    # Parse subsequent rows until footer/blank/non-numeric order
    for line in lines[delim_idx + 1:]:
        if not line:
            break

        low = line.strip().lower()

        # Stop at known footer markers
        if any(m in low for m in footer_markers):
            break
        # Broad catch for similar footer phrasing
        if "end of" in low and "summary" in low:
            break
        # Stop at NOTE/Note variants
        if "note" in low and ":" in low:
            break

        # Stop when the first field ("Order") is no longer numeric
        # This is the most robust footer detector across FTS variants.
        first_width = widths[0] if widths else 0
        if first_width > 0:
            order_val = line[starts[0]:starts[0] + first_width].strip()
        else:
            order_val = line[starts[0]:].strip()
        if not order_val.isdigit():
            break

        row: List[str] = []
        for start, width in zip(starts, widths):
            if width <= 0:
                # If width is zero or nonsensical, take remainder of line for last field
                val = line[start:].strip()
            else:
                val = line[start:start + width].strip()
            row.append(val)

        for h, v in zip(headers, row):
            table[h].append(v)

    return table


def fts_schema(fts_file: str, col_field: str = "Column", type_field: str = "SAS Type") -> Dict[str, str]:
    """
    Robustly extract a {column_name: type_string} mapping from an FTS table.
    """
    table = read_fts_table(fts_file)
    headers = list(table.keys())

    # normalize header text for fuzzy matching
    def norm(h: str) -> str:
        s = re.sub(r"[^A-Za-z ]+", " ", h)
        s = re.sub(r"\s+", " ", s).strip().lower()
        return s

    norm_headers = [norm(h) for h in headers]

    col_idx = None
    type_idx = None

    hint_col = norm(col_field)
    hint_type = norm(type_field)

    # First pass: fuzzy substring match
    for i, nh in enumerate(norm_headers):
        if hint_col and hint_col in nh:
            col_idx = i
        if hint_type and hint_type in nh:
            type_idx = i

    # Generic substring matches if hints didn't catch them
    if col_idx is None:
        for i, nh in enumerate(norm_headers):
            if "column" in nh or nh.endswith(" column") or nh.startswith("column"):
                col_idx = i
                break

    if type_idx is None:
        for i, nh in enumerate(norm_headers):
            if "sas type" in nh or ("sas" in nh and "type" in nh) or ("sas" in nh and nh.endswith(" type")):
                type_idx = i
                break

    # Final fallback: common positional heuristic (column in index 1, type in index 2)
    if col_idx is None or type_idx is None:
        if len(headers) >= 3:
            if col_idx is None:
                col_idx = 1
            if type_idx is None:
                type_idx = 2

    if col_idx is None or type_idx is None:
        raise ValueError(
            f"FTS missing expected fields: col_field={col_field!r}, type_field={type_field!r}. "
            f"Found headers: {headers}"
        )

    columns_raw = table[headers[col_idx]]
    types_raw = table[headers[type_idx]]

    # Filter blanks and normalize types
    type_dict: Dict[str, str] = {}
    for c, t in zip(columns_raw, types_raw):
        c = (c or "").strip()
        if not c:
            continue
        t = (t or "").strip() or "CHAR"
        type_dict[c] = t

    return type_dict


def extract_fixedwidth_schema_from_fts_table(
    fts_table: Dict[str, List[str]]
) -> Tuple[List[str], List[int], List[int], Dict[str, str]]:
    """
    Extract (headers, widths, starts, type_map) for fixed-width DAT parsing.

    Expects the FTS table to contain the typical columns in positions similar to
     DAT parsing: Column names (keys[2]), SAS types (keys[3]), starts (keys[4]), widths (keys[5]).
    """
    keys = list(fts_table.keys())
    if len(keys) < 6:
        raise ValueError("FTS does not contain expected metadata fields for fixed-width parsing.")

    headers = fts_table[keys[2]]
    type_map = dict(zip(headers, fts_table[keys[3]]))
    starts = list(map(int, fts_table[keys[4]]))
    widths_raw = fts_table[keys[5]]

    widths: List[int] = []
    for i, w in enumerate(widths_raw[:-1]):
        try:
            widths.append(int(float(w)))
        except (ValueError, TypeError):
            # fallback to using the start positions
            widths.append(starts[i + 1] - starts[i])

    # last width fallback: try to parse last width, otherwise append 0 to indicate remainder
    try:
        widths.append(int(float(widths_raw[-1])))
    except (ValueError, TypeError):
        widths.append(0)

    return headers, widths, starts, type_map


