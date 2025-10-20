import pytest

from PipeDSL import lexer
from PipeDSL.lexer import tokenizer, Job, CallFunction, Context, Product, ProductParam, ResultFunction, PositionalArg


def test_tokenizer_simple():
    r = "pipeline_context >>"

    delimiters = {
        " ",
        ">>",
        ",",
        ".",
        "(",
        ")"
    }

    assert list(tokenizer(r, delimiters)) == ['pipeline_context', ' ', '>>']


def test_tokenizer():
    r = "pipeline_context >> auth_registration(concat(uuid(), pipeline_context.email_prefix), uuid()) >>products_partner_authorized_user(auth_registration.token)"

    system_tokens = {
        " ",
        ">>",
        ",",
        ".",
        "(",
        ")"
    }

    assert list(tokenizer(r, system_tokens)) == ['pipeline_context', ' ', '>>', ' ', 'auth_registration', '(', 'concat', '(', 'uuid',
                                                 '(', ')', ',', ' ', 'pipeline_context', '.', 'email_prefix', ')', ',', ' ', 'uuid',
                                                 '(', ')', ')', ' ', '>>', 'products_partner_authorized_user', '(',
                                                 'auth_registration', '.', 'token', ')']


def test_tokenizer_3():
    r = "pipeline_context >> registration(uuid1(),uuid2(),uuid3())"

    delimiters = {
        " ",
        ">>",
        ",",
        ".",
        "(",
        ")"
    }

    assert list(tokenizer(r, delimiters)) == ['pipeline_context', ' ', '>>', ' ', 'registration', '(', 'uuid1', '(', ')', ',', 'uuid2', '(',
                                              ')', ',', 'uuid3', '(', ')', ')']


def test_make_ast_one_job():
    ast = lexer.make_ast(
        source="registration()",
        function_names=["registration"],
        properties_names=[],
    )
    assert ast == (Context(pipeline_uuid=''), [Job[CallFunction](payload=CallFunction(name='registration', arguments=[]))])

    ast = lexer.make_ast(
        source="registration(uuid())",
        function_names=["registration"],
        properties_names=[],
    )
    assert ast == (Context(pipeline_uuid=''), [
        Job[CallFunction](payload=CallFunction(name='registration', arguments=[CallFunction(name='uuid', arguments=[])])), ])


def test_make_ast_deep():
    ast = lexer.make_ast(
        source="registration(uuid(uuid()))",
        function_names=["registration"],
        properties_names=[],
    )
    assert ast == (Context(pipeline_uuid=''), [
        Job[CallFunction](payload=CallFunction(name='registration', arguments=[CallFunction(name='uuid', arguments=[CallFunction(name='uuid', arguments=[])])])), ])


    ast = lexer.make_ast(
        source="registration(uuid(uuid(uuid())))",
        function_names=["registration"],
        properties_names=[],
    )

    assert ast == (Context(pipeline_uuid=''), [Job[CallFunction](payload=CallFunction(name='registration', arguments=[CallFunction(name='uuid', arguments=[CallFunction(name='uuid', arguments=[CallFunction(name='uuid', arguments=[])])])])),])

def test_make_ast_two_args():
    ast = lexer.make_ast(
        source="registration(uuid(), uuid())",
        function_names=["registration"],
        properties_names=[],
    )
    assert ast == (Context(pipeline_uuid=''), [Job[CallFunction](payload=CallFunction(name='registration', arguments=[CallFunction(name='uuid', arguments=[]), CallFunction(name='uuid', arguments=[])]))])



def test_make_ast_three_args():
    ast = lexer.make_ast(
        source="registration(uuid1(),uuid2(),uuid3())",
        function_names=["uuid1", "uuid2", "uuid3", "registration"],
        properties_names=[],
    )
    assert ast == (
        Context(pipeline_uuid=''),
        [Job[CallFunction](payload=CallFunction(name='registration', arguments=[CallFunction(name='uuid1', arguments=[]), CallFunction(name='uuid2', arguments=[]), CallFunction(name='uuid3', arguments=[])]))],
    )


def test_unexpected_token():
    with pytest.raises(ValueError) as excinfo:
        ast = lexer.make_ast(
            source="pipeline_context >> registration(uuid1(),uuid2(),uuid3())",
            function_names=["uuid1", "uuid2", "uuid3"],
            properties_names=[],
        )


def test_tokenizer_production():
    r = "[pipeline_context.endpoint] * [registration(A) >> registration(A)]"

    delimiters = {
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
    print(list(tokenizer(r, delimiters)))
    assert list(tokenizer(r, delimiters)) == ['[', 'pipeline_context', '.', 'endpoint', ']', ' ', '*', ' ', '[', 'registration', '(', 'A',
                                              ')', ' ', '>>', ' ', 'registration', '(', 'A', ')', ']']


def test_make_ast_product_jobs():
    ast = lexer.make_ast(
        source="[pipeline_context.endpoint] * [registration($1) >> registration($1)] >> registration()",
        function_names=["registration"],
        properties_names=['endpoint'],
    )
    assert ast == (
        Context(pipeline_uuid=''),
        [
            Job[Product](payload=Product(cartesian_operands=[ProductParam(payload=ResultFunction(name='pipeline_context', property='endpoint'))],
                                         pipeline=[
                                             Job[CallFunction](payload=CallFunction(name='registration', arguments=[PositionalArg(idx=1)])),
                                             Job[CallFunction](
                                                 payload=CallFunction(name='registration', arguments=[PositionalArg(idx=1)]))])),
            Job[CallFunction](payload=CallFunction(name='registration', arguments=[])),
        ],

    )
