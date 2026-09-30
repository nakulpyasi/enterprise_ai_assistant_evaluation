import json
import os
import time
from pathlib import Path

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv
from openai.types.eval_create_params import DataSourceConfigCustom

load_dotenv()

DATASET_PATH = Path("data/generated_outputs.jsonl")

AZURE_AI_PROJECT_ENDPOINT = os.getenv("AZURE_AI_PROJECT_ENDPOINT")
AZURE_AI_MODEL_DEPLOYMENT_NAME = os.getenv("AZURE_AI_MODEL_DEPLOYMENT_NAME")


# Validate required settings.
if not AZURE_AI_PROJECT_ENDPOINT:
    raise RuntimeError("AZURE_AI_PROJECT_ENDPOINT is not set in the .env file.")

if not AZURE_AI_MODEL_DEPLOYMENT_NAME:
    raise RuntimeError("AZURE_AI_MODEL_DEPLOYMENT_NAME is not set in the .env file.")

if not DATASET_PATH.exists():
    raise FileNotFoundError(
        "Generated dataset is missing. Run collect_responses.py first."
    )


# Describe the fields contained in each JSONL row.
data_source_config = DataSourceConfigCustom(
    type="custom",
    item_schema={
        "type": "object",
        "properties": {
            "id": {
                "type": "string",
            },
            "category": {
                "type": "string",
            },
            "query": {
                "type": "string",
            },
            "response": {
                "type": "string",
            },
            "ground_truth": {
                "type": "string",
            },
            "expected_agents": {
                "type": "array",
                "items": {"type": "string"},
            },
            "actual_agents": {
                "type": "array",
                "items": {"type": "string"},
            },
            "status_code": {
                "type": ["integer", "null"],
            },
            "request_id": {
                "type": "string",
            },
            "success": {
                "type": "boolean",
            },
            "error": {
                "type": ["string", "object", "null"],
            },
        },
        "required": [
            "id",
            "category",
            "query",
            "response",
            "ground_truth",
            "expected_agents",
            "actual_agents",
            "status_code",
            "request_id",
            "success",
            "error",
        ],
    },
)


# Define the evaluators Foundry should run.
testing_criteria = [
    {
        "type": "azure_ai_evaluator",
        "name": "similarity",
        "evaluator_name": "builtin.similarity",
        "data_mapping": {
            "query": "{{item.query}}",
            "response": "{{item.response}}",
            "ground_truth": "{{item.ground_truth}}",
        },
        "initialization_parameters": {
            "deployment_name": AZURE_AI_MODEL_DEPLOYMENT_NAME,
            "threshold": 3,
        },
    },
    {
        "type": "azure_ai_evaluator",
        "name": "relevance",
        "evaluator_name": "builtin.relevance",
        "data_mapping": {
            "query": "{{item.query}}",
            "response": "{{item.response}}",
        },
        "initialization_parameters": {
            "deployment_name": AZURE_AI_MODEL_DEPLOYMENT_NAME,
            "threshold": 3,
        },
    },
    {
        "type": "azure_ai_evaluator",
        "name": "response_completeness",
        "evaluator_name": "builtin.response_completeness",
        "data_mapping": {
            "response": "{{item.response}}",
            "ground_truth": "{{item.ground_truth}}",
        },
        "initialization_parameters": {
            "deployment_name": AZURE_AI_MODEL_DEPLOYMENT_NAME,
            "threshold": 3,
        },
    },
    {
        "type": "azure_ai_evaluator",
        # Name displayed as the result metric.
        "name": "routing_correctness",
        # Exact custom evaluator name from the Foundry catalog.
        "evaluator_name": "routing-correctness",
        "initialization_parameters": {
            "pass_threshold": 1.0,
        },
    },
]


def load_evaluation_items() -> list[dict]:
    """Load evaluation items from the generated JSONL dataset."""

    with DATASET_PATH.open("r", encoding="utf-8") as file:
        items = [json.loads(line) for line in file if line.strip()]

    if not items:
        raise ValueError("No evaluation items were found in the dataset.")

    return items


def run_evaluation() -> None:
    """Upload the dataset and run the Foundry evaluation."""

    evaluation_items = load_evaluation_items()
    print(f"Loaded {len(evaluation_items)} evaluation items.")

    project_client = AIProjectClient(
        endpoint=AZURE_AI_PROJECT_ENDPOINT,
        credential=DefaultAzureCredential(),
    )

    evaluation_client = project_client.get_openai_client()

    dataset_version = time.strftime("%Y%m%d%H%M%S")

    # Upload generated_outputs.jsonl to Foundry.
    dataset = project_client.datasets.upload_file(
        name="enterprise-assistant-evaluation-data",
        version=dataset_version,
        file_path=str(DATASET_PATH),
    )

    print(f"Uploaded dataset version: {dataset_version}")
    print(f"Dataset ID: {dataset.id}")

    # Create the evaluation definition.
    evaluation = evaluation_client.evals.create(
        name=f"enterprise-assistant-evaluation-{dataset_version}",
        data_source_config=data_source_config,
        testing_criteria=testing_criteria,
    )

    print(f"Evaluation ID: {evaluation.id}")

    # Start an evaluation run using the uploaded dataset.
    evaluation_run = evaluation_client.evals.runs.create(
        eval_id=evaluation.id,
        name=f"enterprise-assistant-run-{dataset_version}",
        data_source={
            "type": "jsonl",
            "source": {
                "type": "file_id",
                "id": dataset.id,
            },
        },
    )

    print(f"Evaluation run ID: {evaluation_run.id}")
    print(f"Initial status: {evaluation_run.status}")

    # Check every five seconds until the evaluation finishes.
    while True:
        evaluation_run = evaluation_client.evals.runs.retrieve(
            eval_id=evaluation.id,
            run_id=evaluation_run.id,
        )

        print(f"Current status: {evaluation_run.status}")

        if evaluation_run.status in {
            "completed",
            "failed",
            "canceled",
        }:
            break

        time.sleep(5)

    if evaluation_run.status == "completed":
        print("Evaluation completed successfully.")

        report_url = getattr(evaluation_run, "report_url", None)

        if report_url:
            print(f"Foundry report: {report_url}")
    else:
        error = getattr(evaluation_run, "error", None)
        raise RuntimeError(
            f"Evaluation ended with status " f"{evaluation_run.status}. Error: {error}"
        )


if __name__ == "__main__":
    run_evaluation()
