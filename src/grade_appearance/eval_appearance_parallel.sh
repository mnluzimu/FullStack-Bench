DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd $DIR/../..

log_dir=$1

python src/grade_appearance/eval_appearance_parallel.py $log_dir \
    --num-workers 4
