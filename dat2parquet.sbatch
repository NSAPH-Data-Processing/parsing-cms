#!/bin/bash

#SBATCH -p serial_requeue # partition (queue)
#SBATCH -c 4 
#SBATCH --mem 144GB 
#SBATCH --array=0-1
#SBATCH -t 2-00:00 

DAT_FILE="/n/dominici_nsaph_l3/Lab/data/ci3_d_medicare/original_data/cms_medicare/data/10411/2017/medpar_all_file_res000017155_req010411_2017_002.dat"
OUTPUT="/n/dominici_nsaph_l3/Lab/data/data_warehouse/dw_raw_medicare"
CHUNK_SIZE=$((5*10**6))
START_ROW=$(( SLURM_ARRAY_TASK_ID * CHUNK_SIZE ))

echo "Processing $DAT_FILE from row $START_ROW with chunk size $CHUNK_SIZE"

# Run Python script
python src/dat2parquet.py $DAT_FILE $OUTPUT $START_ROW $CHUNK_SIZE --verbose
