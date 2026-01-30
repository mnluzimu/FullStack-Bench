import os
from tqdm import tqdm
import json
import shutil


PRIMARY_CATEGORIES = [
"Content Presentation",
"User Interaction",
"Data Management"
]


def load_json(in_file):
    with open(in_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data


def save_json(data, out_file):
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(data, f)
        

def load_jsonl(in_file):
    datas = []
    with open(in_file, "r", encoding="utf-8") as f:
        for line in tqdm(f):
            datas.append(json.loads(line))
    return datas


def save_jsonl(datas, out_file, mode="w"):
    with open(out_file, mode, encoding="utf-8") as f:
        for data in tqdm(datas):
            f.write(json.dumps(data, ensure_ascii=False) + "\n")


def backend_compute_acc(in_dir):
    categories = {}
    db_categories = {}
    for cat in PRIMARY_CATEGORIES:
        categories[cat] = {
            "yes_num": 0,
            "no_num": 0,
            "start_failed_num": 0,
            "score": 0,
            "total": 0,
            "accuracy": 0
        }

        db_categories[cat] = {
            "yes_num": 0,
            "no_num": 0,
            "start_failed_num": 0,
            "score": 0,
            "total": 0,
            "accuracy": 0
        }

    result_dir = os.path.join(in_dir, "results_backend")
    
    test_file = r"data/WebGen-Bench_test-db-backend.json"
    test_datas = load_json(test_file)
    total = 0
    for data in test_datas:
        total += len(data["backend_test_cases"])
        cat = data["Category"]["primary_category"]
        categories[cat]["total"] += len(data["backend_test_cases"])
        db_categories[cat]["total"] += len(data["backend_test_cases"])

    tasks = [f for f in os.listdir(result_dir) if os.path.isdir(os.path.join(result_dir, f))]
    score = 0
    yes_num = 0
    no_num = 0

    db_score = 0
    db_yes_num = 0
    db_no_num = 0

    # no_sample_dir = os.path.join(in_dir, "no_backend")
    # os.makedirs(no_sample_dir, exist_ok=True)
    
    for task in tqdm(tasks):
        if not os.path.exists(os.path.join(result_dir, task, "testing_result.json")):
            print(f"testing_result.json not found in {task}, skipping...")
            continue
        
        index = int(task.replace("task", "").split("_")[0]) - 1
        sub_index = int(task.replace("task", "").split("_")[1])
        cat = test_datas[index]["Category"]["primary_category"]
        
        data = load_json(os.path.join(result_dir, task, "testing_result.json"))
        text = data["judgement"]

        db_result_file = os.path.join(result_dir, task, "db_interaction_result.json")
        if os.path.isfile(db_result_file):
            db_result = load_json(db_result_file)
            db_judgement = db_result["judgement"]
            if db_judgement == "YES":
                db_weight = 1
            else:
                db_weight = 0
        if text == "YES":
            score += 1
            yes_num += 1
            db_score += db_weight
            db_yes_num += db_weight

            categories[cat]["yes_num"] += 1
            categories[cat]["score"] += 1

            db_categories[cat]["yes_num"] += db_weight
            db_categories[cat]["score"] += db_weight

        else:
            no_num += 1
            categories[cat]["no_num"] += 1

            # shutil.copytree(os.path.join(result_dir, task), os.path.join(no_sample_dir, task))

    for cat in categories:
        categories[cat]["start_failed_num"] = categories[cat]["total"] - categories[cat]["yes_num"] - categories[cat]["no_num"]
        categories[cat]["accuracy"] = categories[cat]["score"] / categories[cat]["total"] * 100 if categories[cat]["total"] > 0 else 0

        db_categories[cat]["start_failed_num"] = categories[cat]["start_failed_num"]
        db_categories[cat]["no_num"] = db_categories[cat]["total"] - db_categories[cat]["yes_num"] - db_categories[cat]["start_failed_num"]
        db_categories[cat]["accuracy"] = db_categories[cat]["score"] / db_categories[cat]["total"] * 100 if db_categories[cat]["total"] > 0 else 0

    start_failed_num = total - yes_num - no_num
    print(f"start_failed: {start_failed_num}")
    test_name = os.path.basename(in_dir)
    yes_rate = yes_num / total * 100
    no_rate = no_num / total * 100
    start_failed_rate = start_failed_num / total * 100
    accuracy = score / total * 100

    db_start_failed_num = start_failed_num
    db_yes_rate = db_yes_num / total * 100
    db_no_num = total - db_yes_num - db_start_failed_num
    db_no_rate = db_no_num / total * 100
    db_start_failed_rate = db_start_failed_num / total * 100
    db_accuracy = db_score / total * 100

    table = f"| test_name | yes_num | no_num | start_failed_num | total | yes_rate | no_rate | start_failed_rate | accuracy |" + " | ".join(PRIMARY_CATEGORIES) + " |\n"
    table += "|------|------|------|------|------|------|------|------|------|" + "------|" * len(PRIMARY_CATEGORIES) + "\n"
    table += f"| {test_name} (backend) | {yes_num} | {no_num}  | {start_failed_num} | {total} | {yes_rate:.1f} | {no_rate:.1f} | {start_failed_rate:.1f} | {accuracy:.1f} |" + " | ".join([f"{categories[cat]['accuracy']:.1f}" for cat in (PRIMARY_CATEGORIES)]) + " |\n"
    table += f"| {test_name} (backend_db) | {db_yes_num} | {db_no_num}  | {db_start_failed_num} | {total} | {db_yes_rate:.1f} | {db_no_rate:.1f} | {db_start_failed_rate:.1f} | {db_accuracy:.1f} |" + " | ".join([f"{db_categories[cat]['accuracy']:.1f}" for cat in (PRIMARY_CATEGORIES)]) + " |\n"
    
    print(f"Saving detailed results to {os.path.join(in_dir, 'table.md')}...")
    with open(os.path.join(in_dir, "table_backend.md"), "w", encoding="utf-8") as f:
        f.write(table)
        
    print(table)

        
def main():
    from argparse import ArgumentParser
    parser = ArgumentParser()
    parser.add_argument("in_dir", type=str)
    args = parser.parse_args()
    
    backend_compute_acc(args.in_dir)

if __name__ == "__main__":
    main()