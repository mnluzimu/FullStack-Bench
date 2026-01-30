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

in_dir=/mnt/cache/agent/Zimu/WebGen-Bench/outputs/TDDev/qwen3coder480B_extracted
log_dir=/mnt/cache/agent/Zimu/WebGen-Bench/outputs/TDDev/qwen3coder480B_logs

python src/ui_test_tddev/ui_eval_with_answer.py \
    --in_dir $in_dir \
    --log_dir $log_dir

