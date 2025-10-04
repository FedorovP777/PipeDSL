# PipeDSL — Declarative HTTP Pipeline Orchestration

PipeDSL is a lightweight framework for defining and executing sequences of HTTP requests using a YAML-based DSL. It supports chaining tasks, passing data between steps, parallel execution, and extracting structured values from JSON responses using JSONPath.

Use PipeDSL to:
- Automate multi-step API workflows
- Build integration or end-to-end tests
- Fetch and transform data across multiple endpoints
- Define complex request pipelines with minimal code

---

## Quick Start

Install the package:

```bash
pip install pipedsl
```

Run a pipeline from a YAML string:

```python
import asyncio
from pipedsl import YamlTaskReader, TaskScheduler

config = """
tasks:
  - type: http
    id: get_user
    name: Fetch user
    url: https://httpbin.org/get
    method: get
    single: false

  - type: http
    id: log_action
    name: Log action
    url: https://httpbin.org/post
    method: post
    body: '{"source": "!{{1}}"}'
    single: false

  - type: pipeline
    id: user_flow
    name: User workflow
    pipeline: "get_user() >> log_action(get_user.url)"
"""

async def main():
    tasks = YamlTaskReader.generate_tasks(config_body=config)
    async for task, result in TaskScheduler.schedule(tasks):
        print(f"Completed {task.id} → {result.payload_type}")

asyncio.run(main())
```

> Note: `TaskScheduler.schedule()` is an async generator. Use `async for` to consume results.

---

## Writing Pipelines

### Basic HTTP Task

```yaml
tasks:
  - type: http
    id: healthcheck
    name: Health check
    url: https://api.example.com/health
    method: get
```

### Sequential Execution

```yaml
tasks:
  - type: http
    id: login
    url: https://api.example.com/login
    method: post
    body: '{"email": "user@example.com"}'
    json_extractor_props:
      token: 'access_token'
    single: false

  - type: http
    id: profile
    url: https://api.example.com/profile
    method: get
    headers:
      - ["Authorization", "Bearer !{{1}}"]
    single: false

  - type: pipeline
    id: auth_flow
    pipeline: "login() >> profile(login.token)"
```

The expression `profile(login.token)` passes the `token` field extracted from the `login` response as the first argument (`!{{1}}`) to the `profile` request.

### Parallel Execution with Product Operator

```yaml
tasks:
  - type: http
    id: list_ids
    url: https://api.example.com/items
    method: get
    json_extractor_props:
      ids: '$.results[*].id'
    single: false

  - type: http
    id: fetch_item
    url: https://api.example.com/items/!{{1}}
    method: get
    single: false

  - type: pipeline
    id: bulk_fetch
    pipeline: "list_ids() >> [list_ids.ids] * [fetch_item($1)]"
```

The syntax `[A] * [B($1)]` means: for each element in `A`, execute `B`, substituting the element as `$1`. This enables fan-out patterns and bulk operations.

---

## Task Reference

| Field | Required | Description |
|------|----------|-------------|
| `id` | Yes | Unique identifier (used in DSL expressions) |
| `name` | No | Human-readable label |
| `type` | Yes | Either `http` or `pipeline` |
| `single` | No | If `true` (default), the task runs standalone. If `false`, it can be called from a pipeline. |
| `url`, `method`, `headers`, `body` | Yes (for `http`) | Standard HTTP request parameters |
| `json_extractor_props` | No | Maps `{name: JSONPath}` to extract values from JSON responses |
| `pipeline_context` | No (for `pipeline`) | Key-value store available as `pipeline_context.key` in DSL |

Placeholders like `!{{1}}`, `!{{2}}`, etc., are replaced with positional arguments during execution.

---

## How It Works

1. **Parsing**: The DSL string (e.g., `login() >> profile(login.token)`) is tokenized and parsed into an abstract syntax tree (AST) using NLTK and a context-free grammar.
2. **Execution**: Tasks are scheduled asynchronously. Results are stored in an execution context under the task’s `id`.
3. **Data Flow**: Expressions like `task.property` resolve to extracted values from prior responses.
4. **Parallelism**: The product operator (`[X] * [Y($1)]`) expands into a Cartesian product and executes sub-pipelines in parallel.

---

## Architecture

- **`YamlTaskReader`**: Reads YAML and builds task definitions with compiled ASTs for pipelines.
- **`TaskScheduler`**: Orchestrates execution of top-level (`single: true`) tasks.
- **`PipelineExecutor`**: Interprets the AST, manages context, and handles sequential/parallel execution.
- **`HttpRequestExecutor`**: Sends requests via `aiohttp` and processes responses.

All core models are immutable (Pydantic with `frozen=True`), and the system is fully typed.

---

## Development

To set up a development environment:

```bash
git clone https://github.com/yourname/PipeDSL.git
cd PipeDSL
pip install -e .
pytest
```

---

## License

Apache License 2.0. See [LICENSE](LICENSE) for details.