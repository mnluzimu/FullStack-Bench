# OpenHands Evaluation

### Installation

```bash
# install the conda environment
cd openhands
conda create -p env/openhands python=3.12
conda activate env/openhands
pip install -r requirements.txt
```

Then, paste workspace.py to `env/openhands/lib/python3.12/site-packages/openhands/workspace/docker/workspace.py`.

### Inference

Add openai-like model name and base url as `LLM_MODEL` and `LLM_BASE_URL` in `.env`

```bash
# run the inference script
bash baselines/openhands/run/batch_run.sh
```