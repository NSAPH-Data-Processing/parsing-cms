import os
import re
import json
import glob
from pathlib import Path
from hydra import compose, initialize

# Update to match your snakemake config name
configfile: "conf/snakemake.yaml"

file_type = config.get("file_type", "auto")  # auto|dat|csv|sas
chunk_size_rows = int(config.get("chunk_size") or 0)  # 0 => single "chunk" for dat/sas
dir_structure = config.get("dir_structure", "year/file_stem")  # year/file_stem or file_stem/year
run_qc = bool(config.get("run_qc", True))
verbose = bool(config.get("verbose", True))
years = config.get("years", None)  # optional list like [2016, 2017]
stems = config.get("stems", None)  #optional to restrict to specific stems
sas_encoding = config.get("sas_encoding", "latin1")  # used by parsecms.chunkplan
input_globs = config.get("input_globs", None)  # optional list of globs (relative to dataset input root)

# hydra config
with initialize(config_path="conf", version_base=None):
    cfg = compose(config_name="config")

dataset = cfg.datapaths.name

# -----------------------------------------------------------------------------
# data roots
# -----------------------------------------------------------------------------
# repo layout convention:
#   data/<dataset>/
#     input  -> symlink to real raw data location
#     output -> folder or symlink to parquet output location
data_root = os.path.join("data", dataset)
input_dir = os.path.join(data_root, config["input_dir"])
output_dir = os.path.join(data_root, config["output_dir"])

supported_exts = {".dat", ".sas7bdat", ".sas", ".csv"}

# -----------------------------------------------------------------------------
# output patterns
# -----------------------------------------------------------------------------

if dir_structure == "year/file_stem":
    outdir_pattern = os.path.join(output_dir, "{year}", "{stem}")
else:
    outdir_pattern = os.path.join(output_dir, "{stem}", "{year}")

part_pattern = os.path.join(outdir_pattern, "part-{chunk}.parquet")
qc_pattern = os.path.join(outdir_pattern, "qc_report.json")

# "done marker" files are lightweight targets that help enforce ordering
csv_done_pattern = "logs/csv_done/{year}/{stem}.done"
parse_done_pattern = "logs/parsed_done/{year}/{stem}.done"

# wildcard validation (snakemake will enforce these regexes)
wildcard_constraints:
    year=r"\d{4}",
    chunk=r"\d{2}"


# -----------------------------------------------------------------------------
# helper functions
# -----------------------------------------------------------------------------
def detect_parser_type(path: str) -> str:
    """
    Determine which parser to use based on the file extension.
    """
    ext = Path(path).suffix.lower()
    if ext == ".dat":
        return "dat"
    if ext in [".sas7bdat", ".sas"]:
        return "sas"
    if ext == ".csv":
        return "csv"
    raise ValueError(f"unsupported file extension: {ext}")


def year_from_name(path: str) -> str:
    """
    Extract a 4-digit year from common cms filenames.

    Example matches:
      *_2016.dat
      *_2016_001.dat
      *_2016.csv
      *_2006_1.sas7bdat
      *2002.sas7bdat
    """
    name = os.path.basename(path)
    m = re.search(r"_?(\d{4})(?:_\d+)?(?:\.|$)", name)
    return m.group(1) if m else "unknown"


def dat_file_stem(path: str) -> str:
    """
    Compute the output stem for dat files.

    Behavior:
      - strip trailing _YYYY
      - if a chunk suffix exists (_YYYY_001) keep it as __001 in the stem
    """
    name = os.path.basename(path)
    base = os.path.splitext(name)[0]
    chunk_match = re.search(r"_(\d{4})(?:_(\d{3}))?$", base)
    if chunk_match:
        chunk_part = chunk_match.group(2)
        if chunk_part:
            return re.sub(r"_(\d{4})_(\d{3})$", r"__\2", base)
        else:
            return re.sub(r"_(\d{4})$", "", base)
    return base


def csv_file_stem(path: str) -> str:
    """
    Compute output stem for csv files:
      - strip trailing _YYYY and optional _NNN
    """
    name = os.path.basename(path)
    base = os.path.splitext(name)[0]
    return re.sub(r"_(\d{4})(?:_\d{3})?$", "", base)


def sas_dataset_name(path: str) -> str:
    """
    Compute output stem for sas files:
      - remove the year substring and tidy separators
    """
    name = os.path.basename(path)
    stem = os.path.splitext(name)[0]
    yr = year_from_name(path)
    return stem.replace(yr, "").rstrip("_").rstrip("-") or stem


def filestem_for(path: str, parser_type: str) -> str:
    """
    Route to the correct stem function based on parser type.
    """
    if parser_type == "dat":
        return dat_file_stem(path)
    if parser_type == "csv":
        return csv_file_stem(path)
    if parser_type == "sas":
        return sas_dataset_name(path)
    raise ValueError(parser_type)


def out_dir_actual(year: str, stem: str) -> str:
    """
    Resolve the concrete output directory for a given (year, stem),
    matching dir_structure.
    """
    if dir_structure == "year/file_stem":
        return os.path.join(output_dir, year, stem)
    else:
        return os.path.join(output_dir, stem, year)


def iter_year_dirs():
    """
    Yield (year, year_dir) pairs under the dataset input directory.

    - if `years` is provided and non-empty, only yields those years
    - otherwise, auto-discovers folders named exactly YYYY under input_dir
    """
    if years is not None:
        yrs = [str(y) for y in years if str(y).strip()]
        if not yrs:
            yrs = None
    else:
        yrs = None

    if yrs is not None:
        for y in yrs:
            yd = os.path.join(input_dir, y)
            if os.path.isdir(yd):
                yield y, yd
    else:
        if not os.path.isdir(input_dir):
            return
        for entry in sorted(os.listdir(input_dir)):
            yd = os.path.join(input_dir, entry)
            if os.path.isdir(yd) and re.fullmatch(r"\d{4}", entry):
                yield entry, yd


# -----------------------------------------------------------------------------
# discover inputs
# -----------------------------------------------------------------------------
# maps are keyed by (year, stem) so downstream rules can use consistent wildcards.
#
# folder-level preference (when file_type=auto):
#   - if any .dat exists anywhere in the selected file list for that year -> parse only dat
#   - elif any .csv exists -> parse only csv
#   - elif any .sas exists -> parse only sas

input_map = {}  # (year, stem) -> file path
type_map = {}   # (year, stem) -> parser type
items = []      # list[{"year","stem","type","file"}]

for year, ydir in iter_year_dirs():
    # collect candidate files for this year
    #
    # if input_globs is provided, each pattern is relative to input_dir and may
    # include {year}. example:
    #   input_globs:
    #     - "{year}/denominator/*.sas7bdat"
    #     - "{year}/inpatient/*.sas7bdat"
    #
    # if input_globs is not set, default to looking directly under input_dir/YYYY/
    files = []
    if input_globs:
        for pat in input_globs:
            rel = pat.format(year=year)
            files.extend(glob.glob(os.path.join(input_dir, rel)))
    else:
        files = [os.path.join(ydir, f) for f in sorted(os.listdir(ydir))]

    # keep only real files with supported extensions
    files = [p for p in files if os.path.isfile(p)]
    files = [p for p in files if Path(p).suffix.lower() in supported_exts]

    # determine type presence to apply folder-level preference
    has_dat = any(Path(p).suffix.lower() == ".dat" for p in files)
    has_csv = any(Path(p).suffix.lower() == ".csv" for p in files)
    has_sas = any(Path(p).suffix.lower() in {".sas", ".sas7bdat"} for p in files)

    # decide which types to keep in this year folder
    if file_type != "auto":
        chosen_types = {file_type}
    else:
        if has_dat:
            chosen_types = {"dat"}
        elif has_csv:
            chosen_types = {"csv"}
        elif has_sas:
            chosen_types = {"sas"}
        else:
            chosen_types = set()

    # build maps keyed by (year, stem)
    for p in files:
        ptype = detect_parser_type(p)
        if ptype not in chosen_types:
            explain = f"(filtered out by folder-level preference; chosen_types={sorted(chosen_types)})"
            continue

        stem = filestem_for(p, ptype)
        _stems_filter = [str(s).strip() for s in stems if str(s).strip()] if stems else None
        if _stems_filter is not None and not any(stem.startswith(s) for s in _stems_filter):
            continue

        key = (year, stem)

        # prevent two different files writing to the same output directory
        if key in input_map and input_map[key] != p:
            raise ValueError(
                f"collision: multiple inputs map to same output dir year/stem={key}:\n"
                f"  - {input_map[key]}\n"
                f"  - {p}\n"
                f"fix by filtering file_type, adjusting input_globs, or updating naming rules."
            )

        input_map[key] = p
        type_map[key] = ptype
        items.append({"year": year, "stem": stem, "type": ptype, "file": p})

if not items:
    raise ValueError(
        f"no input files discovered.\n"
        f"checked input_dir={input_dir}\n"
        f"expected something like {input_dir}/YYYY/*.(dat|sas7bdat|sas|csv)\n"
        f"config years={years}, file_type={file_type}, input_globs={input_globs}\n"
    )

dat_sas_items = [it for it in items if it["type"] in {"dat", "sas"}]
csv_items = [it for it in items if it["type"] == "csv"]


# -----------------------------------------------------------------------------
# final targets
# -----------------------------------------------------------------------------

rule all:
    input:
        (
            [os.path.join(out_dir_actual(it["year"], it["stem"]), "qc_report.json") for it in items]
            if run_qc else
            [f"logs/parsed_done/{it['year']}/{it['stem']}.done" for it in dat_sas_items] +
            [f"logs/csv_done/{it['year']}/{it['stem']}.done" for it in csv_items]
        )


# -----------------------------------------------------------------------------
# checkpoint: compute how many chunks dat/sas needs
# -----------------------------------------------------------------------------
# for dat/sas, we plan the number of chunks from the file itself (rows) and the
# configured chunk_size_rows. this writes a json file with n_chunks.
checkpoint plan_chunks:
    input:
        lambda wc: input_map[(wc.year, wc.stem)]
    output:
        json="logs/chunkplan/{year}/{stem}.json"
    params:
        ptype=lambda wc: type_map[(wc.year, wc.stem)],
        chunk_size=chunk_size_rows,
        sas_encoding=sas_encoding
    shell:
        r"""
        python -m parsecms.chunkplan \
          --input-file {input} \
          --parser-type {params.ptype} \
          --chunk-size {params.chunk_size} \
          --sas-encoding {params.sas_encoding} \
          --out-json {output.json}
        """


def planned_parts(wc):
    """
    Given (year, stem), return the list of expected part parquet outputs.

    Important snakemake detail:
      - when building the initial dag, the checkpoint has not run yet
      - so we return the checkpoint json path first, which forces snakemake
        to schedule the checkpoint and then re-evaluate this function later
    """
    ck = checkpoints.plan_chunks.get(year=wc.year, stem=wc.stem)
    plan_json = ck.output.json

    if not os.path.exists(plan_json):
        return plan_json

    with open(plan_json) as f:
        n = int(json.load(f)["n_chunks"])

    chunks = [f"{i:02d}" for i in range(1, n + 1)]
    return expand(part_pattern, year=wc.year, stem=wc.stem, chunk=chunks)


# -----------------------------------------------------------------------------
# dat/sas parsing (one job per chunk)
# -----------------------------------------------------------------------------
# each job runs run_parser.py on a slice of rows, producing one part-XX.parquet.
rule parse_chunk:
    input:
        src=lambda wc: input_map[(wc.year, wc.stem)]
    output:
        parquet=part_pattern
    params:
        ptype=lambda wc: type_map[(wc.year, wc.stem)],
        start_row=lambda wc: (int(wc.chunk) - 1) * (chunk_size_rows if chunk_size_rows > 0 else 0),
        chunk_size=lambda wc: (chunk_size_rows if chunk_size_rows > 0 else 10**18)
    log:
        "logs/parse/{year}/{stem}_chunk_{chunk}.log"
    shell:
        r"""
        python run_parser.py \
          hydra.run.dir=logs/{wildcards.year}/{wildcards.stem}/{wildcards.chunk} \
          parser_type={params.ptype} \
          input_file={input.src} \
          output_path={output_dir} \
          start_row={params.start_row} \
          chunk_size={params.chunk_size} \
          dir_structure={dir_structure} \
          run_qc=false \
          verbose={verbose} \
          2>&1 | tee {log}
        """


# -----------------------------------------------------------------------------
# dat/sas completion marker
# -----------------------------------------------------------------------------
# this creates a lightweight marker file after all chunk outputs exist.
# qc can depend on this marker to ensure it runs after parsing completes.
rule parsed_done:
    input:
        # force checkpoint into the dag
        plan=lambda wc: checkpoints.plan_chunks.get(year=wc.year, stem=wc.stem).output.json,
        # then expand chunk outputs
        parts=planned_parts
    output:
        done=parse_done_pattern
    shell:
        r"""
        mkdir -p $(dirname {output.done})
        touch {output.done}
        """


# -----------------------------------------------------------------------------
# csv parsing (single-shot)
# -----------------------------------------------------------------------------
# csv parsing is not chunked. we still create a done marker so qc can depend on it.
rule parse_csv:
    input:
        src=lambda wc: input_map[(wc.year, wc.stem)]
    output:
        done=csv_done_pattern
    log:
        "logs/parse/{year}/{stem}_csv.log"
    shell:
        r"""
        python run_parser.py \
          hydra.run.dir=logs/{wildcards.year}/{wildcards.stem}/csv \
          parser_type=csv \
          input_file={input.src} \
          output_path={output_dir} \
          dir_structure={dir_structure} \
          run_qc=false \
          verbose={verbose} \
          2>&1 | tee {log}
        && mkdir -p $(dirname {output.done}) \
        && touch {output.done}
        """


# -----------------------------------------------------------------------------
# qc prerequisites
# -----------------------------------------------------------------------------
def qc_prereq(wc):
    """
    Return the correct "done marker" dependency for qc based on file type.
    """
    ptype = type_map[(wc.year, wc.stem)]
    if ptype in {"dat", "sas"}:
        return f"logs/parsed_done/{wc.year}/{wc.stem}.done"
    else:
        return f"logs/csv_done/{wc.year}/{wc.stem}.done"


# -----------------------------------------------------------------------------
# quality control
# -----------------------------------------------------------------------------
# qc runs on the parquet output directory and infers the correct .fts using the
# original input file path.
rule qc:
    input:
        parsed=qc_prereq
    output:
        qc=qc_pattern
    params:
        parquet_dir=lambda wc: out_dir_actual(wc.year, wc.stem),
        source=lambda wc: input_map[(wc.year, wc.stem)]
    log:
        "logs/qc/{year}/{stem}.log"
    shell:
        r"""
        python -m parsecms.raw_qc \
          --parquet-dir {params.parquet_dir} \
          --infer-fts-from-input {params.source} \
          --qc-output {output.qc} \
          2>&1 | tee {log}
        """

