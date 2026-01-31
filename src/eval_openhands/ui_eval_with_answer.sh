DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd $DIR/../..

npm config set script-shell /bin/sh
export PNPM_SCRIPT_SHELL=/bin/sh
export PATH=/bin:/usr/bin:$PATH

in_dir=$1
log_dir=$2

python src/eval_openhands/ui_eval_with_answer.py \
    --in_dir $in_dir \
    --log_dir $log_dir