"""Make control modules read-only at runtime.

After `freeze(__name__)` any attempt to rebind or delete a module attribute
(e.g. `control.spend_limit.DAILY_LIMIT_WEI = 10**30`) raises PermissionError.
Constants exposed by control modules are immutable types (int, str, tuple,
frozenset, MappingProxyType), so they cannot be mutated in place either.
"""
import sys
import types


class ControlTamperError(PermissionError):
    """Raised when code tries to override a control-layer value."""


class _FrozenModule(types.ModuleType):
    def __setattr__(self, name, value):
        raise ControlTamperError(f"{self.__name__}.{name} is read-only (control layer)")

    def __delattr__(self, name):
        raise ControlTamperError(f"{self.__name__}.{name} cannot be deleted (control layer)")


def freeze(module_name: str) -> None:
    sys.modules[module_name].__class__ = _FrozenModule


freeze(__name__)
