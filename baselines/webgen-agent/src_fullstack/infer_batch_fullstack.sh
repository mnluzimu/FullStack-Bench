DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd $DIR

model_name=Qwen3-Coder-480B-A35B-Instruct-FP8


until python infer_batch_fullstack.py \
    --model ${model_name} \
    --vlm_model Qwen3-VL-32B-Instruct \
    --fb_model ${model_name} \
    --data-path /mnt/cache/agent/Zimu/datasets/WebGen-Bench.jsonl \
    --workspace-root /mnt/cache/agent/Zimu/WebGen-Agent/workspaces_root \
    --log-root /mnt/cache/agent/Zimu/WebGen-Agent/service_logs \
    --max-iter 20 \
    --num-workers 8 \
    --eval-tag fullstack_new \
    --error-limit 5 \
    --max-tokens -1 \
    --max-completion-tokens -1 \
    --temperature 0.5
    # --overwrite
do
    echo "Run failed (exit code $?). Retrying in 10 s…"
    sleep 10
done
