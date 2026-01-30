__conda_setup="$('/root/miniconda3/bin/conda' 'shell.bash' 'hook' 2> /dev/null)"
if [ $? -eq 0 ]; then
    eval "$__conda_setup"
else
    if [ -f "/root/miniconda3/etc/profile.d/conda.sh" ]; then
        . "/root/miniconda3/etc/profile.d/conda.sh"
    else
        export PATH="/root/miniconda3/bin:$PATH"
    fi
fi
unset __conda_setup

conda activate /mnt/cache/agent/Zimu/WebGen-Bench/envwebvoyager_fullstack

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd $DIR/../..

# tmux new-session -s inference
# tmux a -t inference
# bash /mnt/cache/agent/Zimu/WebGen-Bench/src/ui_test_webgen2/ui_eval_with_answer.sh
# run_name=$1
run_name=model-Qwen3-Coder-480B-A35B-Instruct-FP8_hist-100_iter-400_compress-0.5_val-1_sum-5_v9_2
in_dir=/mnt/cache/agent/Zimu/WebGen-Agent2/workspaces_root/$run_name
log_dir=/mnt/cache/agent/Zimu/WebGen-Agent2/logs_root/$run_name

python src/ui_test_webgen2/ui_eval_with_answer.py \
    --in_dir $in_dir \
    --log_dir $log_dir