# Qwen-Code Evaluation

### Installation

```bash
# install the conda environment
cd openhands
conda create -p env/qwen_code python=3.12
conda activate env/qwen_code
pip install -r requirements.txt

# install qwen-code
npm install @qwen-code/qwen-code@0.5.2
```

### Inference

Configure `OPENAI_API_KEY`, `OPENAI_BASE_URL`, and `OPENAI_MODEL` in `.env`.

```bash
# run the inference script
python baselines/qwen-code/src/run/run_batch.py
```