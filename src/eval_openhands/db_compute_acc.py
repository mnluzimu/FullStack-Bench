import os
from tqdm import tqdm
import json


PRIMARY_CATEGORIES = [
"Content Presentation",
"User Interaction",
"Data Management"
]

INST_PRIMARY_CATEGORIES = [
"Functional Testing",
"Data Display Testing",
"Design Validation Testing"
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

        
def db_compute_acc(in_dir):
    print(f"in_dir: {in_dir}")
    categories = {}
    for cat in PRIMARY_CATEGORIES:
        categories[cat] = {
            "yes_num": 0,
            "no_num": 0,
            "total": 0,
            "accuracy": 0
        }
    
    test_file = "/mnt/cache/agent/Zimu/WebGen-Bench/src/generate_fullstack_tests/WebGen-Bench_test-db-backend.json"
    test_datas = load_json(test_file)
    total = 0
    yes_num = 0
    no_num = 0
    outputs = []
    for data in tqdm(test_datas):
        sample_id = data["id"]

        if len(data["data_structures"]) == 0:
            continue
        total += len(data["data_structures"])
        cat = data["Category"]["primary_category"]
        categories[cat]["total"] += len(data["data_structures"])

        db_grade_files = [os.path.join(in_dir, sample_id, f"db_grade_{test_case_id}.json") for test_case_id in range(len(data["data_structures"]))]
        for db_grade_file in db_grade_files:
            if not os.path.isfile(db_grade_file):
                print(f"{db_grade_file} not found in {sample_id}, skipping...")
                continue
        
            db_grade_data = load_json(db_grade_file)
            db_grade_data["id"] = sample_id
            db_grade_data["source"] = os.path.basename(db_grade_file)
            outputs.append(db_grade_data)
            
            if db_grade_data["answer"] == True:
                categories[cat]["yes_num"] += 1
                yes_num += 1
            else:
                categories[cat]["no_num"] += 1
                no_num += 1
            
    for cat in categories:
        categories[cat]["accuracy"] = categories[cat]["yes_num"] / categories[cat]["total"] * 100 if categories[cat]["total"] > 0 else 0

    test_name = os.path.basename(in_dir)
    accuracy = yes_num / total * 100
    table = f"| test_name | db_yes_num | total | db_accuracy |" + " | ".join(PRIMARY_CATEGORIES) + " |\n"
    table += "|------|------|------|------|" + "------|" * len(PRIMARY_CATEGORIES) + "\n"
    table += f"| {test_name} | {yes_num} | {total} | {accuracy:.1f} |" + " | ".join([f"{categories[cat]['accuracy']:.1f}" for cat in (PRIMARY_CATEGORIES)]) + " |\n"
    
    with open(os.path.join(os.path.dirname(in_dir), "table_db.md"), "w", encoding="utf-8") as f:
        f.write(table)

    save_jsonl(outputs, os.path.join(in_dir, "db_grade_results.jsonl"))
        
    print(table)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("in_dir", type=str, help="Input directory containing individual test case results.")
    args = parser.parse_args()

    db_compute_acc(args.in_dir)


if __name__ == "__main__":
    main()