#!/bin/bash

#SBATCH -p serial_requeue # partition (queue)
#SBATCH -c 4 
#SBATCH --mem 96GB 
#SBATCH --array=0-2
#SBATCH -t 2-00:00 

DAT_FILE="/n/dominici_nsaph_l3/Lab/data/ci3_d_medicare/original_data/cms_medicare/data/4334/2012/mbsf_ab_summary_res000017155_req004334_2012.dat"
OUTPUT="/n/dominici_nsaph_l3/Lab/data_processing/shreya_synthetic-cms/synthetic-cms/output"
CHUNK_SIZE=$((2*10**7))
START_ROW=$(( SLURM_ARRAY_TASK_ID * CHUNK_SIZE ))

echo "Processing $DAT_FILE from row $START_ROW with chunk size $CHUNK_SIZE"

# Run Python script
python src/dat2parquet.py $DAT_FILE $OUTPUT $START_ROW $CHUNK_SIZE --verbose
