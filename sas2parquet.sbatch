#!/bin/bash

#SBATCH -p serial_requeue # partition (queue)
#SBATCH -c 4 
#SBATCH --mem 96GB
#SBATCH --array=0-2
#SBATCH -t 2-00:00 

SAS_FILE="/n/dominici_nsaph_l3/Lab/data/ci3_d_medicare/original_data/cms_medicare/data/2000/denominator/dnm2000.sas7bdat"
OUTPUT="/n/dominici_nsaph_l3/Lab/data/data_warehouse/dw_raw_medicare"
CHUNK_SIZE=$((2*10**7))
START_ROW=$(( SLURM_ARRAY_TASK_ID * CHUNK_SIZE ))

echo "Processing $SAS_FILE from row $START_ROW with chunk size $CHUNK_SIZE"

# Run Python script
python src/sas2parquet.py $SAS_FILE $OUTPUT $START_ROW $CHUNK_SIZE --verbose