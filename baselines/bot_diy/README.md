# Bolt.diy Evaluation

### Installation

```bash
# clone the bolt.diy repository and install dependencies
git clone https://github.com/stackblitz-labs/bolt.diy.git
cd bolt.diy
npm install -g pnpm
pnpm install
```

### Inference

We tested this baseline on a windows computer. Before running the inference script, ensure that the bolt.diy services is running on port 5173, and activate the `env\fullstack-bench` conda environment:

```bash
# start bolt.diy
cd bolt.diy
pnpm run dev

# start evaluation
cd FullStack-Bench
baselines\bot_diy\loop.bat
```