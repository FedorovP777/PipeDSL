import yaml

from PipeDSL import lexer
from PipeDSL.models import HttpRequest, Task, Pipeline, TaskType
from PipeDSL.utils.utils import to_2d_array, check_duplicate


def get_task_ids_from_tasks(tasks: list[Task]) -> list[str]:
    return [i.id for i in tasks]


def get_props_from_tasks(tasks: list[Task]) -> list[str]:
    tokens: list[str] = []
    for task in tasks:
        if task.type == "http":
            if hasattr(task.payload, "json_extractor_props"):
                tokens.extend(task.payload.json_extractor_props.keys())

        if task.type == "pipeline":
            if hasattr(task.payload, "pipeline_context"):
                tokens.extend(task.payload.pipeline_context.keys())

    return tokens


class YamlTaskReaderService:
    @staticmethod
    def read_yaml_config(config_body: str) -> list[dict[str, any]]:
        result = yaml.safe_load(config_body)
        assert isinstance(result, dict)
        assert "tasks" in result

        for idx, value in enumerate(result["tasks"]):
            if "headers" in result["tasks"][idx]:
                result["tasks"][idx]["headers"] = list(to_2d_array(result["tasks"][idx]["headers"]))
        return result["tasks"]

    @staticmethod
    def generate_tasks(config_body: str) -> list[Task[Pipeline] | Task[HttpRequest]]:
        tasks = YamlTaskReaderService.read_yaml_config(config_body=config_body)
        result = []

        for task in filter(lambda x: x["type"] == "pipeline", tasks):
            result.append(Task[Pipeline](**task, payload=Pipeline(
                task_id=task["id"],
                pipeline=task["pipeline"],
                http_rps_limit=task.get('http_rps_limit'),
                pipeline_context=dict(task.get("pipeline_context", {}))
            )))
            assert result[-1].is_singleton == True

        for task in filter(lambda x: x["type"] == "http", tasks):
            result.append(Task[HttpRequest](**task, payload=HttpRequest(
                url=task["url"],
                method=task["method"],
                timeout=task.get("timeout", 10),
                body=task.get("body", None),
                headers=dict(task.get("headers", {})),
                json_extractor_props=task.get("json_extractor_props", {})
            )))

        tasks_ids = get_task_ids_from_tasks(result)
        all_props = get_props_from_tasks(result)

        for idx, val in enumerate(result):
            if val.type != "pipeline":
                continue

            ast = lexer.make_ast(
                source=val.payload.pipeline,
                function_names=tasks_ids,
                properties_names=all_props,
            )
            result[idx].payload.ast = ast

        assert check_duplicate([task.id for task in result]) is None, "Task id not unique"

        return result
