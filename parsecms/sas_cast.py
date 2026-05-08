from datetime import date, datetime
from typing import Any, Dict, List
import numpy as np
import pyarrow as pa


def cast_pyreadstat_columns(data: Dict[str, List[Any]], verbose: bool = False) -> Dict[str, pa.Array]:
    """
    Convert pyreadstat output_format='dict' values into pyarrow Arrays.

    Rules:
      - date/datetime -> pa.date64()
      - numeric -> pa.float64()
      - else -> pa.string()
    """
    out: Dict[str, pa.Array] = {}

    for col, values in data.items():
        sample = []
        for v in values:
            if v is None:
                continue
            if isinstance(v, float) and np.isnan(v):
                continue
            sample.append(v)
            if len(sample) >= 10:
                break

        detected = set(type(v) for v in sample)

        if verbose:
            print(f"Column: {col} | Detected Types: {detected}")

        if detected <= {date, datetime}:
            cleaned = [v if isinstance(v, (date, datetime)) else None for v in values]
            out[col] = pa.array(cleaned, type=pa.date64())

        elif detected <= {int, float, np.float64, np.int64} or all(isinstance(v, (int, float, np.integer, np.floating)) or v is None for v in sample):
            cleaned = []
            for v in values:
                if v is None:
                    cleaned.append(None)
                elif isinstance(v, float) and np.isnan(v):
                    cleaned.append(None)
                elif isinstance(v, (int, float, np.integer, np.floating)):
                    cleaned.append(float(v))
                else:
                    cleaned.append(None)
            out[col] = pa.array(cleaned, type=pa.float64())

        else:
            cleaned = [v.strip() if isinstance(v, str) and v.strip() else None for v in values]
            out[col] = pa.array(cleaned, type=pa.string())

    return out
