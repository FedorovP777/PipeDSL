from abc import abstractmethod
from decimal import Decimal
from typing import Callable, Awaitable, Generic, Any

import aiohttp
from aiohttp import ClientSession, ClientResponse
from multidict import istr
from pydantic import BaseModel
from typing_extensions import TypeVar

from PipeDSL.models import HttpRequest


class HttpResponse(BaseModel):
    headers: dict[str, str]
    status_code: int
    execution_time: Decimal | None = None


class TextResponse(HttpResponse):
    body: str | None


class JsonResponse(HttpResponse):
    body: Any


RequestExecutorRetType = TypeVar("RequestExecutorRetType")
ResponseHandlerRetType = TypeVar("ResponseHandlerRetType")
RequestExecutorType = TypeVar("RequestExecutorType")
CredentialProviderRetType = TypeVar("CredentialProviderRetType")


class RequestExecutor(Generic[RequestExecutorRetType]):
    @abstractmethod
    async def execute_request(self, request: HttpRequest) -> RequestExecutorRetType: ...


class AioHttpRequestExecution(RequestExecutor[ClientResponse]):
    def __init__(self, session: ClientSession):
        self.session = session

    async def execute_request(self, request: HttpRequest) -> ClientResponse:
        match request.method.lower():
            case "get":
                return await self._get(request, self.session)
            case "post":
                return await self._post(request, self.session)
        raise NotImplementedError

    async def _get(self, request: HttpRequest, session: ClientSession) -> ClientResponse:
        return await session.get(request.url, headers=request.headers, timeout=aiohttp.ClientTimeout(request.timeout))

    async def _post(self, request: HttpRequest, session: ClientSession) -> ClientResponse:
        return await session.post(request.url, data=request.body, headers=request.headers, timeout=aiohttp.ClientTimeout(request.timeout))


class AsyncHttpClient(Generic[ResponseHandlerRetType, RequestExecutorType, CredentialProviderRetType]):
    def __init__(
            self,
            request_executor: RequestExecutor[ClientResponse],
            response_handler: Callable[[ClientResponse], Awaitable[ResponseHandlerRetType]],
            credential_provider: Callable[[HttpRequest], CredentialProviderRetType] | None = None,
    ):
        self.request_executor = request_executor
        self.credential_provider = credential_provider
        self.response_handler = response_handler

    async def execute_request(self, request: HttpRequest) -> ResponseHandlerRetType:

        if self.credential_provider:
            credential = self.credential_provider(request)
        else:
            credential = None

        response: ClientResponse = await self.request_executor.execute_request(request)
        return await self.response_handler(response)


def none_credential_provider(http_request: HttpRequest) -> None:
    return None


async def response_handler(client_response: ClientResponse) -> TextResponse | JsonResponse:
    if "application/json" in client_response.headers.get(istr("content-type"), "").lower():
        response = await client_response.json()
        client_response.close()
        return JsonResponse(headers=dict(client_response.headers), status_code=client_response.status, body=response)

    response = await client_response.text()
    client_response.close()
    return TextResponse(headers=dict(client_response.headers), status_code=client_response.status, body=response)
