:loop
python src/automatic_bolt_diy_fullstack/eval_bolt_diy.py ^
    --jsonl_path data/WebGen-Bench_test-db-backend.jsonl ^
    --url http://localhost:5173/ ^
    --provider OpenAILike ^
    --desired_model Qwen3-Coder-30B-A3B-Instruct ^
    --tag _set-command
timeout /t 30
goto loop