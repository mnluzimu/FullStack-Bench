
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

attempt=1
while true; do
    echo "────────────────────────────────────────────────────────────"
    echo "Attempt #$attempt: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "Running batch_run.py ..."
    echo "────────────────────────────────────────────────────────────"

    python "$DIR/batch_run.py"
    exit_code=$?

    if [ $exit_code -eq 0 ]; then
        echo "batch_run.py finished successfully (exit code 0)."
        break
    fi

    echo "batch_run.py exited with code $exit_code. Retrying in 5 seconds ..."
    ((attempt++))
    sleep 5
done
