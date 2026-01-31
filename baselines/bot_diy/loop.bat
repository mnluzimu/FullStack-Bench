:loop
python baselines/bolt_diy/eval_bolt_diy.py ^
    --jsonl_path data/FullStack-Bench.jsonl ^
    --url http://localhost:5173/ ^
    --provider OpenAILike ^
    --desired_model Qwen3-Coder-480B-A35B-Instruct-FP8 ^
    --tag _set-command
timeout /t 30
goto loop