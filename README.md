# Enterprise AI Assistant Evaluation

Evaluate an enterprise assistant’s answer quality and agent routing against a small, version-controlled golden dataset. This project collects responses from a deployed assistant API and submits them to Microsoft Foundry for evaluation.

The sample dataset contains five cases covering SQL questions, retrieval-augmented generation (RAG), and hybrid questions that require both agents.

## How it works

1. Read questions and expected answers from `data/golden_dataset.jsonl`.
2. Send each question to your assistant’s `POST /ask` endpoint.
3. Save answers, selected agents, and request metadata to `data/generated_outputs.jsonl`.
4. Upload the generated dataset to Foundry, start an evaluation, and poll for results.

| Evaluation | Purpose | Configured threshold |
| --- | --- | --- |
| Similarity | Compare the response with the reference answer | `3` |
| Relevance | Assess how well the response addresses the question | `3` |
| Response completeness | Compare the response’s coverage with the reference answer | `3` |
| Routing correctness | Evaluate agent selection using a custom evaluator | `pass_threshold=1.0` |

The first three criteria use Foundry built-in evaluators. Routing uses a custom evaluator named `routing-correctness`; its implementation and registration are not included in this repository.

## Prerequisites

- Python 3.11 or newer; the project pins 3.11 in `.python-version`.
- `uv` for dependency management.
- A running assistant API with the contract described below.
- A Microsoft Foundry project and a model deployment suitable for the configured evaluators.
- Azure credentials with permission to upload datasets and run evaluations in that project.
- A custom `routing-correctness` evaluator available in your Foundry project and compatible with the generated dataset.

The assistant service, its knowledge sources, and Azure resources are managed separately from this project.

## Setup

Clone the repository and install the locked dependencies:

```bash
git clone https://github.com/nakulpyasi/enterprise_ai_assistant_evaluation.git
cd enterprise_ai_assistant_evaluation
uv sync --locked
cp .env.example .env
```

Edit `.env` with your settings:

```dotenv
ASSISTANT_API_URL=http://localhost:8000
AZURE_AI_PROJECT_ENDPOINT=https://your-foundry-project-endpoint
AZURE_AI_MODEL_DEPLOYMENT_NAME=your-model-deployment-name
```

| Variable | Used by | Value |
| --- | --- | --- |
| `ASSISTANT_API_URL` | Response collection | Assistant base URL, without `/ask` |
| `AZURE_AI_PROJECT_ENDPOINT` | Evaluation | Project endpoint copied from Foundry |
| `AZURE_AI_MODEL_DEPLOYMENT_NAME` | Evaluation | Deployment name of the model used to grade responses |

Evaluation uses `DefaultAzureCredential`. For local development with Azure CLI installed, sign in to the account that has access to your project:

```bash
az login
```

`.env` and generated response data are excluded from Git by `.gitignore`.

## Assistant API contract

The collector sends the following JSON to `POST {ASSISTANT_API_URL}/ask`:

```json
{"question": "How many support tickets are there?"}
```

A successful response must contain `answer`. The optional `agents_used` field defaults to an empty list:

```json
{
  "answer": "There are 5 support tickets.",
  "agents_used": ["sql_agent"]
}
```

The collector also records the `x-request-id` response header when present. It currently sends no authentication headers; APIs requiring authentication need a corresponding change in `collect_responses.py`.

## Run the pipeline

Run all commands from the repository root because dataset paths are relative to the working directory.

### 1. Collect assistant responses

```bash
uv run python -m enterprise_ai_assistant_evaluation.collect_responses
```

Requests run sequentially with a 120-second HTTP client timeout. Progress is printed for each case, and results are written to `data/generated_outputs.jsonl`. Each run overwrites that file.

Each result preserves the original test case and adds:

| Field | Description |
| --- | --- |
| `response` | Assistant answer, or an empty string on a recorded failure |
| `actual_agents` | Agents reported by the assistant |
| `status_code` | HTTP response status, or `0` for a request error |
| `request_id` | Response request ID, when available |
| `success` | Whether collection succeeded for the case |
| `error` | Error details, or an empty string on success |

Inspect this file before starting evaluation. Failed collection rows are included in evaluation unless you remove them or recollect the responses.

### 2. Run the Foundry evaluation

```bash
uv run python -m enterprise_ai_assistant_evaluation.run_evaluation
```

The script uploads a timestamped version of `enterprise-assistant-evaluation-data`, creates an evaluation and run, and checks the status every five seconds. It prints the dataset ID, evaluation ID, run ID, and a report URL when one is returned. A failed or canceled run raises an error.

This step uploads collected questions, answers, and metadata to your configured Foundry project and uses Azure resources that may incur charges. Results remain in Foundry; the script does not export scores to a local report.

Use the module commands above for the pipeline. The `enterprise-ai-assistant-evaluation` console command currently only prints a greeting.

## Customize the dataset

Add one JSON object per line to `data/golden_dataset.jsonl`:

```json
{"id":"hybrid_001","category":"hybrid","query":"How many support tickets are there and how long is the Acme Hub warranty?","ground_truth":"There are 5 support tickets, and the Acme Hub has a 2-year warranty.","expected_agents":["sql_agent","rag_agent"]}
```

Use a unique `id`, a descriptive `category`, the input `query`, a reference `ground_truth` answer, and an array of `expected_agents`. Match agent names to those returned by your assistant and understood by your routing evaluator.

The bundled cases assume specific sample data, such as five support tickets and Acme product policies. Update the reference answers to match your own database and documents before interpreting scores. After editing the dataset, collect responses again before evaluating.

To change evaluator selection or thresholds, edit `testing_criteria` in `src/enterprise_ai_assistant_evaluation/run_evaluation.py`.

## Project layout

```text
.
├── .env.example                 # Environment configuration template
├── .python-version             # Python version for uv
├── data/
│   └── golden_dataset.jsonl     # Questions, reference answers, expected agents
├── src/enterprise_ai_assistant_evaluation/
│   ├── __init__.py              # Placeholder console entry point
│   ├── collect_responses.py    # Call the assistant and save response data
│   └── run_evaluation.py       # Upload data and run Foundry evaluators
├── scratch.py                  # Local dataset inspection helper with a hardcoded path
├── pyproject.toml              # Package metadata and dependencies
└── uv.lock                     # Locked dependency versions
```

## Troubleshooting

| Problem | What to check |
| --- | --- |
| `ASSISTANT_API_URL is missing` | Set the assistant base URL in `.env`. |
| Azure settings are missing | Set both `AZURE_AI_PROJECT_ENDPOINT` and `AZURE_AI_MODEL_DEPLOYMENT_NAME`. |
| Generated dataset is missing or empty | Run response collection from the repository root and inspect its output. |
| Connection failures or timeouts | Confirm the assistant is running and its `/ask` endpoint is reachable. |
| JSON parsing errors or a missing `answer` | Ensure the API returns JSON, including on errors, and successful responses contain `answer`. |
| Azure authentication or authorization errors | Check your Azure credentials and project permissions. |
| Routing evaluator cannot be found | Register `routing-correctness` in your project or update `testing_criteria` to use an available evaluator. |

The collector records HTTP failures with JSON bodies and HTTP client request errors. Invalid JSON or a missing `answer` in a successful response can stop collection. There are currently no automatic retries or overall evaluation polling timeout.
