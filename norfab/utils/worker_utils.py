import inspect
from typing import Callable


def is_need_argument(function: Callable, argument: str) -> bool:
    """Check whether a callable explicitly declares an argument.

    Args:
        function: Callable whose arguments are inspected.
        argument: Parameter name to look for.

    Returns:
        bool: True for a declared positional or keyword-only parameter,
        including parameters with defaults. Accepting **kwargs alone does
        not count as declaring the argument.
    """
    spec = inspect.getfullargspec(function)
    return argument in spec.args or argument in spec.kwonlyargs
