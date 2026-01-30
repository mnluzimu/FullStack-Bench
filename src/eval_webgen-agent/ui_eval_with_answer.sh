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

in_dir=/mnt/cache/agent/Zimu/WebGen-Agent/workspaces_root/WebGenAgentV3_WebGen-Bench_Qwen3-Coder-30B-A3B-Instruct_iter20_fullstack_new
log_dir=/mnt/cache/agent/Zimu/WebGen-Agent/service_logs/WebGenAgentV3_WebGen-Bench_Qwen3-Coder-30B-A3B-Instruct_iter20_fullstack_new

python src/ui_test_webgen_fullstack/ui_eval_with_answer.py \
    --in_dir $in_dir \
    --log_dir $log_dir