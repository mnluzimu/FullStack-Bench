import glob
import os
import shutil

def remove_node_modules():
    root_dir = "/mnt/cache/agent/Zimu/WebGen-Agent/workspaces_root"
    base_patterns = [
      f"/mnt/cache/agent/Zimu/WebGen-Agent/workspaces_root/{run_name}/000*/node_modules" for run_name in os.listdir(root_dir) if run_name != "WebGenAgentV3_WebGen-Bench_Qwen2_5-Coder-7B-Instruct_711-06071005_ckpt-16_step-GRPO_pen-rep-tmp1_fix-img-grade_WebGen-Instruct_2_501_global_step_25_iter20_select_best_32b-fb_fix-ss-grade"
    ]
    
    # Use glob to find all matching node_modules directories (recursive search).
    directories = []
    for base_pattern in base_patterns:
      directories.extend(glob.glob(base_pattern, recursive=True))
    
    print(directories)
    for dir_path in directories:
        if os.path.isfile(dir_path):
            print(f"Removing: {dir_path}")
            shutil.os.remove(dir_path)
        elif os.path.isdir(dir_path):
            print(f"Removing directory: {dir_path}")
            shutil.rmtree(dir_path)


if __name__ == "__main__":
    remove_node_modules()
