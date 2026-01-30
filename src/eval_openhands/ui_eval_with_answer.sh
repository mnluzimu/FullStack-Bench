__conda_setup="$('/root/miniconda3/bin/conda' 'shell.zsh' 'hook' 2> /dev/null)"
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

npm config set script-shell /bin/sh
export PNPM_SCRIPT_SHELL=/bin/sh
export PATH=/bin:/usr/bin:$PATH

# sudo pkill -9 -f "npm run dev"
# echo '* hard nproc 4096' | sudo tee -a /etc/security/limits.conf


# tmux new-session -s inference
# tmux a -t inference
# bash /mnt/cache/agent/Zimu/WebGen-Bench/src/ui_test_webgen2/ui_eval_with_answer.sh
# run_name=$1
in_dir=/mnt/cache/agent/Zimu/OpenHands/workspaces_root/Openhands_openai/Qwen3-Coder-30B-A3B-Instruct_iter400
log_dir=/mnt/cache/agent/Zimu/OpenHands/workspaces_root/Openhands_openai/Qwen3-Coder-30B-A3B-Instruct_iter400_logs

python src/ui_test_openhands_fullstack/ui_eval_with_answer.py \
    --in_dir $in_dir \
    --log_dir $log_dir