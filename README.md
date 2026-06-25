# parsecms

`parsecms` is a Python package for converting CMS data files (**DAT**, **CSV**, **SAS**) to **Parquet**, driven by **FTS metadata** when available.

Efficient processing of DAT and SAS files is performed **chunk-wise**.

This repo uses:
- **Hydra** for configuration and a unified runner (`run_parser.py`)
- **PyArrow** for reading/writing Parquet (and CSV parsing)
- **DuckDB** for basic QC
- Optional orchestration via **Snakemake** (`Snakefile` + `conf/snakemake.yaml`)

---

## Repository structure

```
.
├── parsecms/
│   ├── __init__.py
│   ├── create_dir_paths.py
│   ├── csv.py
│   ├── dat.py
│   ├── sas.py
│   ├── fts.py
│   ├── raw_qc.py
│   ├── parquetio.py
│   ├── paths.py
│   └── sas_cast.py
├── run_parser.py
├── Snakefile
└── conf/
    ├── config.yaml
    ├── snakemake.yaml
    └── datapaths/
        └── <dataset_name>.yaml
```

---

## Setup

### 1) Activate environment

```bash
micromamba activate nsaph_data_cms_data_prep
```

### 2) Create local data links / folder structure

This repo expects a local `data/` directory in the repo root that contains a per-dataset folder
(based on your Hydra `datapaths.name`):

```
data/<datapaths.name>/
  input  -> symlink to real data location
  output -> symlink or directory for parquet outputs
```

Create directories and symlinks from config:

```bash
python -m parsecms.create_dir_paths datapaths=<dataset_datapaths_config>
```

Example datapaths config (`conf/datapaths/medicaid_max_red.yaml`):

```yaml
name: medicaid_max_red
dirs:
  input: "/path/to/original/cms/data"
  output: "/path/to/data_warehouse/parsing_medicaid_max"
```

---

## Configuration overview

### Hydra configs (single-file runs)

- `conf/config.yaml`: default config for `run_parser.py`
- `conf/datapaths/<name>.yaml`: dataset-specific paths and layout

Hydra configs are composed at runtime and overridden via CLI:
```bash
python run_parser.py datapaths=medicare_sas_red chunk_size=1000000
```

### Snakemake config (workflow runs)

- `conf/snakemake.yaml` controls orchestration only
- Chooses dataset via `datapaths:`
- Controls chunk size, years, QC, verbosity

Snakemake passes only the needed overrides into `run_parser.py`.

---

## Usage

### Single-file parsing (Hydra)

```bash
python run_parser.py \
  datapaths=medicare_sas_red \
  parser_type=dat \
  input_file=/path/to/file_2016.dat \
  output_path=./data/medicaid_taf_red/output \
  chunk_size=1000000 \
  verbose=true
```

### Snakemake orchestration

Dry run:
```bash
snakemake --dryrun --debug-dag
```

Run:
```bash
snakemake --cores 4
```

---

## Quality Control

QC is DuckDB-based and may run automatically or standalone.

Standalone:
```bash
python -m parsecms.raw_qc \
  --parquet-dir ./data/<dataset>/output/2016/<stem> \
  --infer-fts-from-input /path/to/file_2016.dat
```
