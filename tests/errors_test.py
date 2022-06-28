import pytest

from aiobtclientrpc import _errors

rpc_exception_map = {
    r'^The environment is perfectly safe$': ValueError(r'RUN FOR YOUR LIVES!'),
    r'^The (\w+) fell (\w+)$': (ValueError, r'\1: I fell \2!'),
    r'^A (?P<what>\w+) hit the (?P<who>\w+)$': (ValueError, r'\g<who>: I was hit by a \g<what>!'),
    r'\{([^\}]*?)\}': (ValueError, r'<\1>'),
}

@pytest.mark.parametrize(
    argnames='rpc_error, exp_return_value',
    argvalues=(
        (_errors.RPCError('The environment is perfectly safe'), ValueError(r'RUN FOR YOUR LIVES!')),
        (_errors.RPCError('The environment is toppled over'), _errors.RPCError('The environment is toppled over')),

        (_errors.RPCError('The front fell off'), ValueError(r'front: I fell off!')),
        (_errors.RPCError('The bottom fell off'), ValueError(r'bottom: I fell off!')),
        (_errors.RPCError('The front escalated quickly'), _errors.RPCError('The front escalated quickly')),

        (_errors.RPCError('A wave hit the ship'), ValueError(r'ship: I was hit by a wave!')),
        (_errors.RPCError('A whale hit the blimp'), ValueError(r'blimp: I was hit by a whale!')),
        (_errors.RPCError('A whale punched the blimp'), _errors.RPCError('A whale punched the blimp')),

        (_errors.RPCError('Some {text with} braces'), ValueError(r'<text with>')),
        (_errors.RPCError('Some {text} with {braces}'), ValueError(r'<text>')),
    ),
    ids=lambda v: repr(v),
)
def test_RPCError_translate_finds_matching_exception_with_backreferences(rpc_error, exp_return_value):
    return_value = rpc_error.translate(rpc_exception_map)
    assert type(return_value) is type(exp_return_value)
    assert str(return_value) == str(exp_return_value)
