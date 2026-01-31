# TDDev Evaluation

### Installation

```bash
# install the tddev conda environment
cd tddev
conda create -p env/tddev python=3.12.11 -y
conda activate env/tddev
pip install -r requirements.txt

# install other dependencies
playwright install chromium --with-deps
pip install pyyaml docker waitress selenium

# install bolt.diy
cd bolt.diy
npm install -g pnpm
pnpm install
```

### Inference

You might need to configure some variables in `bolt.diy` and `client`. Then run:

```bash
# run the inference script
python baselines/tddev/src/run/automatic_run_fullstack.py
```