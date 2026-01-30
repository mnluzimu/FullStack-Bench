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

run_name=model-Qwen3-Coder-480B-A35B-Instruct-FP8_hist-100_iter-400_compress-0.5_val-1_sum-5_v9_2
in_dir=/mnt/cache/agent/Zimu/WebGen-Agent2/logs_root/${run_name}
# in_dir=/mnt/cache/k12_data/WebGen-Agent2/logs_root/${run_name}

python /mnt/cache/agent/Zimu/WebGen-Bench/src/grade_appearance_webgen2/eval_appearance_parallel.py $in_dir \
    --num-workers 4
