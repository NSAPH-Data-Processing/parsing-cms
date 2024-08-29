# synthetic-cms
Generating synthetic CMS data for AI/ML models and general lab use

## Setup instructions

Using some of the code in this package requires the use of the [`dorieh`](https://github.com/NSAPH-Data-Platform/dorieh/tree/main) python package. As outlined on the [`dorieh` main page](https://github.com/NSAPH-Data-Platform/dorieh/tree/main), follow these steps to install `dorieh` on your device or cluster environment.


```
# create and activate a new conda environment
conda create -n "dorieh"
conda activate dorieh

# install the latest version of dorieh
pip install git+https://github.com/NSAPH-Data-Platform/dorieh
```

If working only on your local device or command line, this should be sufficient to start using `dorieh`. If you're hoping to access `dorieh` from within a Jupyter Notebook on FASSE, you'll need to make the new conda environment "visible" to Jupyter. The FASRC docs suggest following [this procedure](https://docs.rc.fas.harvard.edu/kb/python/):

```
module load python/3.10.9-fasrc01 # or whatever python module you have loaded
mamba activate dorieh
mamba install ipykernel nb_conda_kernels python=3.10.9 # must be current python version
```

Note that this can take some time. 

## Exploring `dorieh` functionality

The root of the `dorieh` python package is not the root of the [`dorieh` GitHub repo](https://github.com/NSAPH-Data-Platform/dorieh/tree/main), but rather `src/python/dorieh`. There is good documentation and explanations for things on [PyPi](https://foromeplatform.github.io/dorieh/), but you can also look through the root of the [python package on GitHub](https://github.com/NSAPH-Data-Platform/dorieh/tree/main/src/python/dorieh) to get a better idea for how things are working under the hood.