import json

if __name__ == "__main__":
    for line in open(
        "/Users/shivikaarora/Documents/nakulnavika_repo/fastapi/enterprise_ai_assistant_evaluation/data/golden_dataset.jsonl"
    ):
        data = json.loads(line)
        print(data)
