# WebGen-Agent Evaluation

### Installation

```bash
# install the conda environment
cd webgen-agent
conda create -p env/webgen-agent python=3.12
conda activate env/webgen-agent
pip install -r requirements.txt
```

### Inference

```bash
# run the inference script
bash baselines/webgen-agent/src_fullstack/infer_batch_fullstack.sh
```