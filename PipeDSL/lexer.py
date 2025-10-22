import copy
from collections.abc import Iterable
from typing import TypeVar, Generic, Generator, Any

import nltk
from nltk.tree.prettyprinter import TreePrettyPrinter
from pydantic import BaseModel
from pydantic import Field

from PipeDSL.utils.logger import logger

SYSTEM_FUNCTIONS = {
    "int",
    "uuid",
    "concat",
    "pipeline_context",
    "pipeline_uuid",
    "div",
    "range",
}

SYSTEM_DELIMITERS = {
    " ",
    ">>",
    ",",
    ".",
    "(",
    ")",
    "*",
    "[",
    "]"
}


def get_grammar(function_names: Iterable[str], properties_names: Iterable[str]) -> nltk.CFG:
    context_free_grammar = nltk.CFG.fromstring(f"""
    S ->  NEXT_STEP
    NEXT_STEP ->  OPTIONAL_EMPTY JOB OPTIONAL_EMPTY | OPTIONAL_EMPTY JOB OPTIONAL_EMPTY NEXT_OP NEXT_STEP 
    JOB -> CALL_FN | PRODUCT
    NEXT_STEP -> 
    NEXT_OP -> '>>'
    PRODUCT_PARAM -> PARAM | PARAM OPTIONAL_EMPTY PARAM_DELIMITER OPTIONAL_EMPTY PRODUCT_PARAM
    PRODUCT -> left_square_bracket PRODUCT_PARAM right_square_bracket OPTIONAL_EMPTY multiply_symbol OPTIONAL_EMPTY left_square_bracket NEXT_STEP right_square_bracket
    PARAM_DELIMITER -> comma_symbol
    OPTIONAL_EMPTY -> space_symbol OPTIONAL_EMPTY
    OPTIONAL_EMPTY -> 
    CALL_FN -> FUNCTION left_bracket OPTIONAL_EMPTY FN_PARAMS OPTIONAL_EMPTY right_bracket
    FN_PARAMS -> PARAM
    FN_PARAMS -> PARAM OPTIONAL_EMPTY PARAM_DELIMITER OPTIONAL_EMPTY FN_PARAMS
    FN_PARAMS -> 
    PARAM -> FUNCTION dot_symbol PROPS
    PARAM -> CALL_FN
    PARAM -> POSITIONAL_ARG
    multiply_symbol -> '*'
    comma_symbol -> ','
    dot_symbol -> '.'
    space_symbol -> ' '
    left_bracket -> '('
    right_bracket -> ')'
    right_square_bracket -> ']'
    left_square_bracket -> '['

    FUNCTION -> 'pipeline_context'
    FUNCTION -> {" | ".join([f"'{i}'" for i in function_names])}
    PROPS ->{" | ".join([f"'{i}'" for i in properties_names])}
    POSITIONAL_ARG ->{" | ".join([f"'${i}'" for i in range(10)])}
    """)
    logger.debug(context_free_grammar)
    return context_free_grammar


class Context(BaseModel):
    pipeline_uuid: str = Field(default_factory=lambda: str())


class ResultFunction(BaseModel):
    name: str
    property: str


class PositionalArg(BaseModel):
    idx: int


class CallFunction(BaseModel):
    name: str
    arguments: "list[ResultFunction | CallFunction | PositionalArg]"


class ProductParam(BaseModel):
    payload: ResultFunction | CallFunction | PositionalArg


T = TypeVar('T')


class Job(BaseModel, Generic[T]):
    payload: T


class Product(BaseModel):
    cartesian_operands: list[ProductParam] = Field(default_factory=list)
    pipeline: "list[Job[Product] | Job[CallFunction]]" = Field(default_factory=list)


def tokenizer(body: str, delimiters: set[str]) -> Generator[str]:
    token = ""
    for i in body:
        if token in delimiters:
            yield token
            token = ""
        if i in delimiters:
            if token:
                yield token
            yield i
            token = ""
        else:
            token += i

    if token:
        yield token


def parse_call_params(tree: nltk.tree.tree.Tree) -> list[ResultFunction | CallFunction | PositionalArg]:
    params = []
    for child in tree:
        match child.label():
            case "FN_PARAMS":
                params.extend(parse_call_params(child))
            case "PARAM":
                match child[0].label():
                    case "CALL_FN":
                        params.append(call_function(child[0]))
                    case "FUNCTION":
                        if len(child) < 3:
                            raise SyntaxError("Malformed PARAM: missing PROPS")

                        params.append(ResultFunction(
                            name=child[0].leaves()[0],
                            property=child[2].leaves()[0]
                        ))
                    case "POSITIONAL_ARG":
                        value = child[0].leaves()[0]
                        if not value.startswith("$"):
                            raise SyntaxError(f"Invalid positional arg: {value}")
                        try:
                            idx = int(value[1:])
                        except ValueError:
                            raise SyntaxError(f"Invalid positional arg index: {value}")
                        params.append(PositionalArg(idx=idx))

    return params


def call_function(tree: nltk.tree.tree.Tree) -> CallFunction:
    function_name = ""
    function_params = None
    for child in tree:
        match child.label():
            case "FUNCTION":
                function_name = child.leaves()[0]
            case "FN_PARAMS":
                function_params = parse_call_params(child)

    return CallFunction(name=function_name, arguments=function_params)


def product_param(tree: nltk.tree.tree.Tree) -> Generator[ProductParam]:
    for child in tree:
        match child.label():
            case "PARAM":
                match child[0].label():
                    case "FUNCTION":
                        yield ProductParam(payload=ResultFunction(name=child[0].leaves()[0], property=child[2].leaves()[0]))
                    case "POSITIONAL_ARG":
                        yield ProductParam(payload=PositionalArg(idx=child[0].leaves()[0].replace("$", "")))
                    case "CALL_FN":
                        yield ProductParam(payload=call_function(child[0]))

            case "PRODUCT_PARAM":
                yield from product_param(child)


def product(tree: nltk.tree.tree.Tree) -> Product:
    product_params: list[ProductParam] = []
    jobs: list[Job[Product] | Job[CallFunction]] = []
    for child in tree:
        match child.label():
            case "PRODUCT_PARAM":
                product_params.extend(product_param(child))
            case "NEXT_STEP":
                jobs.extend(traverse_ast(child))

    return Product(cartesian_operands=product_params, pipeline=jobs)


def traverse_ast(tree: nltk.tree.tree.Tree) -> Generator[Job[Product] | Job[CallFunction]]:
    for child in tree:
        match child.label():
            case "NEXT_STEP":
                yield from traverse_ast(child)
            case "JOB":
                match child[0].label():
                    case "PRODUCT":
                        yield Job[Product](payload=product(child[0]))
                    case "CALL_FN":
                        yield Job[CallFunction](payload=call_function(child[0]))


def lexer(input_tokens: Iterable[str], function_names: Iterable[str], properties_names: Iterable[str]) -> nltk.tree.tree.Tree | None:
    grammar = get_grammar(
        function_names=function_names,
        properties_names=properties_names
    )
    parser = nltk.ChartParser(grammar)
    grammar_count = len(list(parser.parse(input_tokens)))
    assert grammar_count < 2, f"Ambiguous grammar, got {grammar_count}, expected 1"
    return parser.parse_one(input_tokens)


def make_ast(source: str, function_names: tuple[str,...], properties_names: tuple[str,...]) -> tuple[
    Context, list[Job[Product] | Job[CallFunction]]]:
    system_functions = copy.deepcopy(SYSTEM_FUNCTIONS)
    result = lexer(
        input_tokens=list(tokenizer(source, SYSTEM_DELIMITERS)),
        function_names=list(system_functions.union(function_names)),
        properties_names=list(system_functions.union(properties_names))
    )

    if not result:
        raise SyntaxError("Invalid pipeline syntax")

    logger.debug(TreePrettyPrinter(result, None, ()).text())
    root_context = Context()
    jobs = list(traverse_ast(result))
    return root_context, list(jobs)
