import json
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

INPUT_PATH = Path("data/golden_dataset.jsonl")
OUTPUT_PATH = Path("data/generated_outputs.jsonl")

API_URL = os.getenv("ASSISTANT_API_URL")

if not API_URL:
    raise ValueError("ASSISTANT_API_URL is missing Add it to the .env file.")


def load_cases() -> list[dict]:
    """Load all test cases from the golden dataset."""
    with INPUT_PATH.open("r", encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]


def collect_responses() -> None:
    """Call the deployed assistant for every evaluation case"""
    cases = load_cases()

    with httpx.Client(timeout=120.0) as client:
        with OUTPUT_PATH.open("w", encoding="utf-8") as output_file:
            for position, case in enumerate(cases, start=1):
                try:
                    response = client.post(
                        f"{API_URL.rstrip('/')}/ask", json={"question": case["query"]}
                    )

                    response_data = response.json()

                    request_id = response.headers.get("x-request-id", "")

                    if response.is_success:
                        result = {
                            **case,
                            "response": response_data["answer"],
                            "actual_agents": response_data.get("agents_used", []),
                            "status_code": response.status_code,
                            "request_id": request_id,
                            "success": True,
                            "error": "",
                        }
                    else:
                        result = {
                            **case,
                            "response": "",
                            "actual_agents": [],
                            "status_code": response.status_code,
                            "request_id": request_id,
                            "success": False,
                            "error": response_data,
                        }
                except httpx.RequestError as error:
                    result = {
                        **case,
                        "response": "",
                        "actual_agents": [],
                        "status_code": 0,
                        "request_id": "",
                        "success": False,
                        "error": str(error),
                    }

                output_file.write(json.dumps(result, ensure_ascii=False) + "\n")
                output_file.flush()

                print(
                    f"[{position}/{len(cases)}] "
                    f"{case['id']} | "
                    f"success={result['success']} | "
                    f"agents={result['actual_agents']}"
                )

    print(f"Responses collected and saved to {OUTPUT_PATH}")


if __name__ == "__main__":
    collect_responses()
