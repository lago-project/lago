import functools
import inspect
import wrapt


class SDKWrapper(wrapt.ObjectProxy):
    """A proxy object that exposes only methods which were decorated with
    :func:`expose` decorator."""

    def __getattr__(self, name):
        attr = getattr(self.__wrapped__, name)
        return getattr_sdk(attr, name)

    def __dir__(self):
        orig = super(SDKWrapper, self).__dir__()
        filtered = []
        for name in orig:
            attr = getattr(self.__wrapped__, name)
            try:
                getattr_sdk(attr, name)
                filtered.append(name)
            except AttributeError:
                pass
        return filtered


class SDKMethod(object):
    """Metadata to store inside the decorated function"""

    def __init__(self, name):
        self.name = name


def expose(func):
    """
    Decorator to be used with :class:`SDKWrapper`. This decorator indicates
    that the wrapped method or class should be exposed in the proxied object.

    Args:
        func(types.FunctionType/types.MethodType): function to decorate

    Returns:
        None
    """

    @functools.wraps(func)
    def wrapped(*args, **kwargs):
        return func(*args, **kwargs)

    if inspect.isclass(func):
        wrapped._sdkmetaclass = SDKMethod(func.__name__)
    else:
        wrapped._sdkmeta = SDKMethod(func.__name__)
    return wrapped


def getattr_sdk(attr, name):
    """
    Filter SDK attributes

    Args:
        attr(attribute): Attribute as returned by :func:`getattr`.
        name(str): Attribute name.

    Returns:
        `attr` if passed.
    """
    if inspect.isroutine(attr):
        if hasattr(attr, '_sdkmeta'):
            return attr
    raise AttributeError(name)
