from collections.abc import Callable, Sequence
from typing import Any

import yaml

from PipeDSL import lexer
from PipeDSL.models import HttpRequest, Task, Pipeline
from PipeDSL.utils.utils import to_2d_array


class HttpTaskBuilder:
    @staticmethod
    def normalize_headers(raw_headers: Any) -> dict[str, str]:
        if not raw_headers:
            return {}
        header_pairs: list[list[str]] = list(to_2d_array(raw_headers))
        return {str(k).strip(): str(v).strip() for k, v in header_pairs}

    @staticmethod
    def build(raw_task: dict[str, Any]) -> Task[HttpRequest]:
        headers = HttpTaskBuilder.normalize_headers(raw_task.get("headers"))
        payload = HttpRequest(
            url=raw_task["url"],
            method=raw_task["method"],
            timeout=raw_task.get("timeout", 10.0),
            body=raw_task.get("body"),
            headers=headers,
            json_extractor_props=raw_task.get("json_extractor_props") or {},
        )
        return Task[HttpRequest].model_validate({**raw_task, "payload": payload})


class PipelineTaskBuilder:
    @staticmethod
    def build(raw_task: dict[str, Any]) -> Task[Pipeline]:
        payload = Pipeline(
            task_id=raw_task["id"],
            pipeline=raw_task["pipeline"],
            http_rps_limit=raw_task.get("http_rps_limit"),
            fetch_strategy=raw_task.get("fetch_strategy"),
            pipeline_context=raw_task.get("pipeline_context") or {},
        )
        return Task[Pipeline].model_validate({**raw_task, "payload": payload})


# =============== Регистратор типов задач ===============

ConcreteTask = Task[HttpRequest] | Task[Pipeline]
TaskBuilderFn = Callable[[dict[str, Any]], ConcreteTask]

_TASK_BUILDERS: dict[str, TaskBuilderFn] = {
    "http": HttpTaskBuilder.build,
    "pipeline": PipelineTaskBuilder.build,
}


def get_task_ids_from_tasks(tasks: list[Task[Any]]) -> list[str]:
    return [i.id for i in tasks]


def get_props_from_tasks(tasks: list[ConcreteTask]) -> list[str]:
    tokens: list[str] = []
    for task in tasks:
        if task.type == "http":
            if hasattr(task.payload, "json_extractor_props"):
                tokens.extend(task.payload.json_extractor_props.keys())

        if task.type == "pipeline":
            if hasattr(task.payload, "pipeline_context"):
                tokens.extend(task.payload.pipeline_context.keys())

    return tokens


def extract_task_ids(tasks: Sequence[ConcreteTask]) -> list[str]:
    return [task.id for task in tasks]


def extract_property_names(tasks: Sequence[ConcreteTask]) -> list[str]:
    props: list[str] = []
    for task in tasks:
        payload = task.payload
        if isinstance(payload, HttpRequest):
            props.extend(payload.json_extractor_props.keys())
        elif isinstance(payload, Pipeline):
            props.extend(payload.pipeline_context.keys())
    return props


class YamlTaskReaderService:
    @staticmethod
    def parse_yaml_config(config_body: str) -> list[dict[str, Any]]:
        try:
            data = yaml.safe_load(config_body)
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML: {e}") from e

        if not isinstance(data, dict) or "tasks" not in data:
            raise ValueError("YAML must contain a 'tasks' list")
        if not isinstance(data["tasks"], list):
            raise ValueError("'tasks' must be a list")

        for task in data["tasks"]:
            if "headers" in task:
                task["headers"] = list(to_2d_array(task["headers"]))
        return data["tasks"]

    @staticmethod
    def generate_tasks(config_body: str) -> list[ConcreteTask]:
        raw_tasks = YamlTaskReaderService.parse_yaml_config(config_body=config_body)

        built_tasks: list[ConcreteTask] = []

        for raw_task in raw_tasks:
            task_type = raw_task.get("type")

            if task_type not in _TASK_BUILDERS:
                raise ValueError(f"Unsupported task type: {task_type}")

            builder = _TASK_BUILDERS[task_type]
            task = builder(raw_task)
            built_tasks.append(task)

        ids = [t.id for t in built_tasks]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate task IDs are not allowed")

        task_ids = extract_task_ids(built_tasks)
        prop_names = extract_property_names(built_tasks)

        for task in built_tasks:
            if isinstance(task.payload, Pipeline):
                try:
                    ast = lexer.make_ast(
                        source=task.payload.pipeline,
                        function_names=tuple(task_ids),
                        properties_names=tuple(prop_names),
                    )
                    task.payload.ast = ast
                except Exception as e:
                    raise ValueError(f"Failed to parse pipeline in task '{task.id}': {e}") from e

        return built_tasks
