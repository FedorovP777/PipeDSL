from PipeDSL.models import Task, HttpRequest, Pipeline
from PipeDSL.services.generate_task import YamlTaskReaderService


def test_read_task():
    config = """
    .default_headers: &default_headers
      - [ 'Accept', 'a' ]
      - [ 'User-Agent', 'b' ]
      - [ 'Accept-Language:', 'c' ]
    tasks:
      - type: http
        id: 16b4e67a-2f61-4dc2-916a-052c72c58fd5
        name: ABC
        url: https://ya.ru/
        method: get
        headers:
          - *default_headers
        body:
        timeout: 1
    """
    tasks = YamlTaskReaderService.generate_tasks(config_body=config)
    assert len(tasks) == 1
    assert tasks[0].id == "16b4e67a-2f61-4dc2-916a-052c72c58fd5"
    assert tasks[0].type == "http"
    assert tasks[0].name == "ABC"
    assert isinstance(tasks[0].payload, HttpRequest)
    assert tasks[0].payload.body is None
    assert tasks[0].payload.method == "get"
    assert tasks[0].payload.timeout == 1
    assert tasks[0].payload.headers == {'Accept': 'a', 'User-Agent': 'b', 'Accept-Language:': 'c'}


def test_read_pipeline():
    config = """
    .default_headers: &default_headers
      - [ 'Accept', 'a' ]
      - [ 'User-Agent', 'b' ]
      - [ 'Accept-Language:', 'c' ]

    tasks:
      - type: http
        name: registration
        url: '!{{1}}/gateway/v1/auth/email/sign_up/'
        method: post
        headers:
          - *default_headers
        body: '{ "email": "!{{2}}","pass": "!{{3}}" }'
        timeout: 2
        id: registration
        is_singleton: false
        json_extractor_props:
          token: 'token'

      - type: pipeline
        name: ABC
        id: 16b4e67a-2f61-4dc2-916a-052c72c58fd5
        pipeline: "registration(pipeline_context.endpoint, concat(uuid(), pipeline_context.email_prefix), uuid()) "
        pipeline_context:
          email_prefix: '@autotest.test'
          endpoint: 'https://api.com'
    """
    tasks = YamlTaskReaderService.generate_tasks(config_body=config)
    assert len(tasks) == 2
    assert tasks[0].id == "16b4e67a-2f61-4dc2-916a-052c72c58fd5"
    assert tasks[0].type == "pipeline"
    assert tasks[0].name == "ABC"
    assert isinstance(tasks[0].payload, Pipeline)

