DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd $DIR/../..

in_dir=$1
log_dir=$2

python src/ui_test_webgen_fullstack/ui_eval_with_answer.py \
    --in_dir $in_dir \
    --log_dir $log_dir