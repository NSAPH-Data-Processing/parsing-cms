import os
import logging
from pathlib import Path

import hydra
from omegaconf import DictConfig

from parsecms.dat import dat_to_parquet_chunk, fts_for_dat
from parsecms.csv import csv_to_parquet, fts_for_csv
from parsecms.sas import sas_to_parquet_chunk
from parsecms.raw_qc import run_duckdb_qc_on_parquet_dir 

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
LOGGER = logging.getLogger(__name__)


def detect_file_type(filepath: str) -> str:
    ext = Path(filepath).suffix.lower()
    if ext == ".dat":
        return "dat"
    if ext in [".sas7bdat", ".sas"]:
        return "sas"
    if ext == ".csv":
        return "csv"
    raise ValueError(f"Unsupported file type: {ext}")


def run_quality_control(
    cfg: DictConfig,
    parquet_dir: str,
    fts_file: str | None = None,
    qc_output_path: str | None = None,
) -> None:
    """
    Run DuckDB-based QC on a parquet directory.

    - If fts_file exists, we use it for expected schema/shape comparisons.
    - If fts_file is missing/None, QC still runs (no expected schema checks).
    """
    if not cfg.run_qc:
        return

    if not parquet_dir or not os.path.exists(parquet_dir):
        LOGGER.warning(f"QC skipped: parquet_dir does not exist: {parquet_dir}")
        return

    # Resolve QC output path
    if qc_output_path is None:
        qc_output_path = cfg.qc_output
        if qc_output_path in ("auto", None):
            qc_output_path = os.path.join(parquet_dir, "qc_report.json")

    # Only pass FTS if it exists
    fts_arg = fts_file if (fts_file and os.path.exists(fts_file)) else None

    LOGGER.info(
        f"Running quality control on parquet_dir={parquet_dir}"
        + (f" using fts_file={fts_arg}" if fts_arg else " (no FTS available)")
    )

    report = run_duckdb_qc_on_parquet_dir(
        parquet_dir=parquet_dir,
        fts_file=fts_arg,
        qc_output=qc_output_path,
    )

    LOGGER.info(f"QC report saved to {qc_output_path}")
    # Optional: log shape summary
    shape = report.get("shape_check", {})
    LOGGER.info(f"QC shape_check: {shape}")


@hydra.main(config_path="conf", config_name="config", version_base=None)
def main(cfg: DictConfig) -> None:
    if cfg.input_file == "???":
        raise ValueError("input_file must be specified")
    if cfg.output_path == "???":
        raise ValueError("output_path must be specified")

    if not os.path.exists(cfg.input_file):
        raise FileNotFoundError(f"Input file not found: {cfg.input_file}")

    if cfg.parser_type == "auto":
        cfg.parser_type = detect_file_type(cfg.input_file)
        LOGGER.info(f"Auto-detected parser type: {cfg.parser_type}")

    try:
        if cfg.parser_type == "dat":
            out_file = dat_to_parquet_chunk(
                dat_file=cfg.input_file,
                out_root=cfg.output_path,
                start_row=cfg.start_row,
                num_rows=cfg.chunk_size,
                dir_structure=cfg.dir_structure,
                verbose=cfg.verbose,
            )

            if cfg.run_qc and out_file:
                parquet_dir = os.path.dirname(out_file)
                fts_file = fts_for_dat(cfg.input_file)
                run_quality_control(cfg, parquet_dir=parquet_dir, fts_file=fts_file)

        elif cfg.parser_type == "csv":
            out_file = csv_to_parquet(
                csv_file=cfg.input_file,
                out_root=cfg.output_path,
                dir_structure=cfg.dir_structure,
                verbose=cfg.verbose,
            )

            if cfg.run_qc and out_file:
                parquet_dir = os.path.dirname(out_file)
                fts_file = fts_for_csv(cfg.input_file)
                run_quality_control(cfg, parquet_dir=parquet_dir, fts_file=fts_file)

        elif cfg.parser_type == "sas":
            out_file = sas_to_parquet_chunk(
                sas_file=cfg.input_file,
                out_root=cfg.output_path,
                start_row=cfg.get("start_row", 0),
                num_rows=cfg.chunk_size,
                dir_structure=cfg.dir_structure,
                verbose=cfg.verbose,
                encoding=cfg.get("sas_encoding", "latin1"),
            )

            # QC for SAS: usually no FTS. Still run QC if we have an output file path.
            if cfg.run_qc and out_file:
                parquet_dir = os.path.dirname(out_file)
                run_quality_control(cfg, parquet_dir=parquet_dir, fts_file=None)

        else:
            raise ValueError(f"Unknown parser type: {cfg.parser_type}")

        LOGGER.info("=" * 80)
        LOGGER.info("Processing completed successfully!")
        LOGGER.info("=" * 80)

    except Exception as e:
        LOGGER.error(f"Error during processing: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()



