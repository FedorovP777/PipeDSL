import asyncio
import copy
import datetime
import decimal
import itertools
import json
import time
import uuid
from collections.abc import Callable, AsyncGenerator, AsyncIterable
from functools import reduce, partial, singledispatch, singledispatchmethod
from operator import concat
from typing import Any

import aiohttp

from PipeDSL.lexer import Job, CallFunction, ResultFunction, Product, PositionalArg
from PipeDSL.models import HttpRequest, Pipeline, Task, TaskResult, JsonResponse, TextResponse, PipelineJobResult, PipelineResult, \
    TaskPayloadTypesAssocInv, TaskPayloadTypes, EmptyResponse
from PipeDSL.utils import http_client
# from utils.http_client import AsyncHttpClient, AioHttpRequestExecution, json_response_handler
from PipeDSL.utils.logger import logger
from PipeDSL.utils.utils import json_extend_extractor


class DslFunctionUuid:
    name: "uuid"

    async def __call__(self):
        return str(uuid.uuid4())


class DslFunctionConcat:
    name: "concat"

    async def __call__(self, *args, **kwargs):
        return str(reduce(concat, args, ""))


class DslFunctionDiv:
    name: "div"

    async def __call__(self, *args, **kwargs):
        if isinstance(args[0], list):
            return float(args[0][0]) / float(args[1])

        return float(args[0]) / float(args[1])


class DslFunctionRange:
    name: "range"

    async def __call__(self, *args, **kwargs):
        if len(args) == 3:
            start, stop, step = args
            if isinstance(start, list):
                start = start[0]
            if isinstance(stop, list):
                stop = stop[0]
            if isinstance(step, list):
                step = step[0]
            return list(range(int(start), int(stop), int(step)))
        return []


SYSTEM_FUNCTION_REGISTRY: dict[str, Callable[[...], any]] = {
    "uuid": DslFunctionUuid(),
    "concat": DslFunctionConcat(),
    "div": DslFunctionDiv(),
    "range": DslFunctionRange(),
}


def get_task_by_id(tasks: list[Task], _id: str):
    for task in tasks:
        if task.id == _id:
            return task


sem = asyncio.Semaphore(10)


# work with shared resource


class HttpRequestExecutor:

    @staticmethod
    async def execute(http_request: HttpRequest) -> JsonResponse | TextResponse:
        logger.debug(f"Start execute http request: {http_request.url}")
        # await asyncio.wait_for(sem.acquire(), timeout=200)
        async with sem:
            async with aiohttp.ClientSession() as session:
                client = http_client.AsyncHttpClient(http_client.AioHttpRequestExecution(session), http_client.response_handler, None)
                t1_stop = time.perf_counter()
                response = await client.execute_request(http_request)
                t2_stop = time.perf_counter()
                execution_time = decimal.Decimal(t2_stop - t1_stop).quantize(decimal.Decimal('.001'), rounding=decimal.ROUND_DOWN)
                if isinstance(response, http_client.JsonResponse):
                    return JsonResponse(
                        headers=response.headers,
                        body=json.dumps(response.body),
                        status_code=response.status_code,
                        execution_time=execution_time,
                    )
                if isinstance(response, http_client.TextResponse):
                    return TextResponse(
                        headers=response.headers,
                        body=response.body,
                        status_code=response.status_code,
                        execution_time=execution_time)



    @staticmethod
    def compile_http_request_template(job: HttpRequest, args: list[str]) -> HttpRequest:
        job = copy.deepcopy(job)
        for idx, arg in enumerate(args, 1):

            if not isinstance(arg, str):
                logger.warning(f"Expected str, got {type(arg)}")

            arg = str(arg)
            tmpl = "!{{%s}}" % idx
            job.url = job.url.replace(tmpl, arg)

            if job.body:
                job.body = job.body.replace(tmpl, arg)

            job.headers = {k.replace(tmpl, arg): v.replace(tmpl, arg) for k, v in job.headers.items()}
        return job


counter = 0


class PipelineExecutor:

    @staticmethod
    async def execute(task: Task[Pipeline], tasks: list[Task]) -> list[PipelineJobResult]:
        pipeline_context = {
            "tasks": tasks,
            "http_rps_limiter": asyncio.Semaphore(task.payload.http_rps_limit),
            "strategy": "parallel"
        }
        results: list[PipelineJobResult] = []
        assert task.payload.ast
        _, jobs = task.payload.ast

        execution_context = {"pipeline_context": task.payload.pipeline_context}

        for job in jobs:
            task_result = await PipelineExecutor.execute_pipeline_job(job, pipeline_context, execution_context)
            results.extend(task_result)

        return results

    @singledispatchmethod
    @staticmethod
    async def execute_pipeline_job(
            job: Job,
            pipeline_context: dict,
            execution_context: dict,
            group_args_in=None
    ) -> list[PipelineJobResult]:

        raise NotImplementedError(f"Cannot handle a {type(job)}")

    @execute_pipeline_job.register
    @staticmethod
    async def _(job: Job[Product], pipeline_context: dict, execution_context: dict, group_args_in=None) -> list[PipelineJobResult]:

        product_args = []

        for i in job.payload.l_group:
            product_args.append(
                await PipelineExecutor.handle_argument_function(i.payload, pipeline_context, execution_context, group_args_in))

        result = []
        optimization = pipeline_context["strategy"] == "parallel"

        async def execute_jobs(jobs, params):
            nonlocal execution_context
            result_ = []
            e = copy.deepcopy(execution_context)
            for _job in jobs:
                result_.extend(await PipelineExecutor.execute_pipeline_job(_job, pipeline_context, e, params))
            return result_

        if optimization:
            tasks = [execute_jobs(job.payload.r_group, r_group_positional_args) for r_group_positional_args in
                     itertools.product(*product_args)]
            for i in await asyncio.gather(*tasks):
                result.extend(i)


        else:
            for r_group_positional_args in itertools.product(*product_args):
                for sub_job in job.payload.r_group:
                    result.extend(
                        await PipelineExecutor.execute_pipeline_job(sub_job, pipeline_context, execution_context, r_group_positional_args))

        return result

    @execute_pipeline_job.register
    @staticmethod
    async def _(job: Job[CallFunction], pipeline_context: dict, execution_context, group_args=None) -> list[PipelineJobResult]:
        args = []
        sub_task = get_task_by_id(pipeline_context["tasks"], job.payload.name)

        if not sub_task:
            raise SyntaxError(f"Undefined function: {job.payload.name}")

        tasks = []
        optimization = False

        if optimization:
            for i in job.payload.arguments:
                tasks.append(PipelineExecutor.handle_argument_function(i, pipeline_context, copy.deepcopy(execution_context), group_args))

            result = await asyncio.gather(*tasks)

            for i in result:
                if isinstance(i, list):
                    args.append(i[0])
                else:
                    args.append(i)
        else:
            for i in job.payload.arguments:
                result = await PipelineExecutor.handle_argument_function(i, pipeline_context, execution_context, group_args)

                if isinstance(result, list):
                    result = result[0]

                args.append(result)

        logger.debug(f"Execute job: {job.payload.name}, props: {args}")
        compiled_job = HttpRequestExecutor.compile_http_request_template(sub_task.payload, args)
        logger.debug(f"Request compiled: {job}")

        consumed_task = await HttpRequestExecutor.execute(compiled_job)
        task_result = PipelineJobResult(
            id=str(uuid.uuid4()),
            created_at=str(datetime.datetime.now().isoformat()),
            task_id=sub_task.id,
            request=compiled_job,
            result=consumed_task,
            args=[str(i) for i in args],
        )
        execution_context[job.payload.name] = {k: json_extend_extractor(v, consumed_task.body) for k, v in
                                               sub_task.payload.json_extractor_props.items()}
        return [task_result]

    @staticmethod
    async def execute_function(pipeline_context: dict, execution_context, fn: CallFunction, group_args=None):
        args = []

        for i in fn.arguments:
            args.append(await PipelineExecutor.handle_argument_function(i, pipeline_context, execution_context, group_args))
        fn = SYSTEM_FUNCTION_REGISTRY[fn.name]
        return await fn(*args)

    @singledispatch
    @staticmethod
    async def handle_argument_function(arg, pipeline_context: dict, execution_context, group_args=None):
        raise NotImplementedError(f"Cannot handle argument type {type(arg)}")

    @handle_argument_function.register
    @staticmethod
    async def handle_argument_function_(arg: ResultFunction, pipeline_context: dict, execution_context, group_args=None):
        return execution_context[arg.name][arg.property]

    @handle_argument_function.register
    @staticmethod
    async def handle_argument_function_(arg: CallFunction, pipeline_context: dict, execution_context, group_args=None):
        result = await PipelineExecutor.execute_function(pipeline_context, execution_context, arg, group_args)
        return result

    @handle_argument_function.register
    @staticmethod
    async def handle_argument_function_(arg: PositionalArg, pipeline_context: dict, execution_context, group_args):
        return group_args[arg.idx - 1]


ExecuteTaskResult = AsyncIterable[tuple[Task, TaskResult]]


class TaskScheduler:

    @staticmethod
    async def schedule(tasks: list[Task]) -> AsyncGenerator[tuple[Task, TaskResult], Any]:
        _get_task_by_id = partial(get_task_by_id, tasks)
        for task in tasks:
            if not task.single:
                continue

            async for i in TaskScheduler.execute_task(task, tasks):
                yield i

        logger.info(f"Execute tasks done, count tasks {len(tasks)}")

    @singledispatch
    @staticmethod
    async def execute_task(task: Task, tasks: list[Task]) -> ExecuteTaskResult:
        raise NotImplementedError(f"Task type not implemented: {type(task)}")

    @execute_task.register
    @staticmethod
    async def _execute_task(task: Task[Pipeline], tasks: list[Task]) -> ExecuteTaskResult:
        _get_task_by_id = partial(get_task_by_id, tasks)
        job_result_ids = []
        try:
            jobs = await PipelineExecutor.execute(task, tasks)
        except TimeoutError as e:
            yield task, TaskResult[EmptyResponse](
                id=str(uuid.uuid4()),
                created_at=str(datetime.datetime.now().isoformat()),
                task_id=task.id,
                payload=None,
                payload_type=TaskPayloadTypes.EMPTY,
                is_throw=True,
                error_description="TimeoutError",
                status="fail"
            )
            return

        for job in jobs:
            sub_task = _get_task_by_id(job.task_id)
            result_id = str(uuid.uuid4())
            job_result_ids.append(result_id)

            yield sub_task, TaskResult[type(job.result)](
                id=result_id,
                created_at=str(datetime.datetime.now().isoformat()),
                task_id=sub_task.id,
                payload_type=TaskPayloadTypesAssocInv[type(job.result)],
                payload=job.result,
                request=job.request,
                args=job.args,
            )

        yield task, TaskResult[PipelineResult](
            id=str(uuid.uuid4()),
            created_at=str(datetime.datetime.now().isoformat()),
            task_id=task.id,
            payload=PipelineResult(task_id=task.id, status="done", job_results=job_result_ids),
            payload_type=TaskPayloadTypes.PIPELINE,
            status="done"
        )

    @execute_task.register
    @staticmethod
    async def _execute_task(task: Task[HttpRequest], tasks: list[Task]) -> ExecuteTaskResult:
        is_throw = False
        error_description = ""

        try:
            payload = await HttpRequestExecutor.execute(task.payload)
            logger.debug(f"Done execute http request")
        except TimeoutError as e:
            raise e
            error_description = "TimeoutError"
            is_throw = True
            payload = EmptyResponse

        yield task, TaskResult[type(payload)](
            id=str(uuid.uuid4()),
            created_at=str(datetime.datetime.now().isoformat()),
            request=task.payload,
            payload=payload,
            payload_type=TaskPayloadTypesAssocInv[type(payload)],
            task_id=task.id,
            is_throw=is_throw,
            error_description=error_description,
        )
