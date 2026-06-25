import os
import re
from typing import Literal, Tuple

DirStructure = Literal["year/file_stem", "file_stem/year"]


def output_dir(out_root: str, year: str, file_stem: str, dir_structure: DirStructure) -> str:
    if dir_structure == "year/file_stem":
        return os.path.join(out_root, year, file_stem)
    if dir_structure == "file_stem/year":
        return os.path.join(out_root, file_stem, year)
    raise ValueError("Invalid dir_structure. Use 'year/file_stem' or 'file_stem/year'.")


def ensure_output_dir(out_root: str, year: str, file_stem: str, dir_structure: DirStructure) -> str:
    out_dir = output_dir(out_root, year, file_stem, dir_structure)
    os.makedirs(out_dir, exist_ok=True)
    return out_dir


def dat_bucket_parts(file_name: str) -> Tuple[str, str]:

    base = os.path.splitext(os.path.basename(file_name))[0]

    m = re.search(r"_(\d{4})(?:_\d{3}|$)", base)
    year = m.group(1) if m else os.path.basename(file_name)

    chunk_match = re.search(r"_(\d{4})(?:_(\d{3}))?$", base)
    if chunk_match:
        chunk_part = chunk_match.group(2)
        if chunk_part:
            file_stem = re.sub(r"_(\d{4})_(\d{3})$", r"__\2", base)
        else:
            file_stem = re.sub(r"_(\d{4})$", "", base)
    else:
        file_stem = base

    return year, file_stem


def csv_bucket_parts(file_name: str) -> Tuple[str, str]:
    base = os.path.splitext(os.path.basename(file_name))[0]
    m = re.search(r"_(\d{4})", os.path.basename(file_name))
    year = m.group(1) if m else "unknown"
    file_stem = re.sub(r"_(\d{4})(?:_\d{3})?$", "", base)
    return year, file_stem


def sas_bucket_parts(file_name: str) -> Tuple[str, str]:
    stem = os.path.splitext(os.path.basename(file_name))[0]
    m = re.search(r"(\d{4})", stem)
    year = m.group(1) if m else os.path.basename(file_name)
    dataset = stem.replace(year, "").rstrip("_").rstrip("-")
    if not dataset:
        dataset = stem
    return year, dataset
