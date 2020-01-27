import pytest
import types

import six

from lago import sdk_utils


class MockExposed(object):
    def __init__(self, **kwargs):
        for key, value in six.iteritems(kwargs):
            if value is True:

                def dummy_method(self):
                    pass

                if six.PY2:
                    method = types.MethodType(dummy_method, self, MockExposed)
                else:
                    method = types.MethodType(dummy_method, self)

                setattr(self, key, sdk_utils.expose(method))


class TestSDKWrapper(object):
    @pytest.mark.parametrize(
        'exposed,not_exposed', [
            ([], []), (['exposed_1'], []), ([], ['exposed_2']),
            (['exposed_1', 'exposed_2'], []),
            (['exposed_1', 'exposed_2'], ['exposed_3']),
            (['exposed_1', '__default'], ['exposed_4'])
        ]
    )
    def test_SDKWrapper_attrs(self, exposed, not_exposed):
        params = {func: True for func in exposed}
        params.update({func: False for func in not_exposed})
        original = MockExposed(**params)
        wrapped = sdk_utils.SDKWrapper(original)

        dir_wrapped = dir(wrapped)
        for value in exposed:
            assert hasattr(wrapped, value)
            assert value in dir_wrapped

        for value in not_exposed:
            with pytest.raises(AttributeError):
                getattr(wrapped, value)
            assert value not in dir_wrapped


class TestSDKUtils(object):
    def test_getattr_sdk_method(self):
        name = 'method'

        def func(self):
            pass

        setattr(func, '_sdkmeta', True)
        attr = types.MethodType(func, object)
        assert attr == sdk_utils.getattr_sdk(attr, name)

    def test_getattr_sdk_function(self):
        name = 'function'
        attr = lambda x: True  # noqa: E731
        attr._sdkmeta = True
        assert attr == sdk_utils.getattr_sdk(attr, name)

    @pytest.mark.parametrize('attr,name', [('a', 'a'), ('b_b', 'b')])
    def test_getattr_sdk_attribute_negative(self, attr, name):
        with pytest.raises(AttributeError):
            sdk_utils.getattr_sdk(attr, name)

    def test_getattr_sdk_method_negative(self):
        name = 'method'

        def func(self):
            pass

        attr = types.MethodType(func, object)
        with pytest.raises(AttributeError):
            sdk_utils.getattr_sdk(attr, name)

    def test_getattr_sdk_function_negative(self):
        name = 'function'
        attr = lambda x: True  # noqa: E731
        with pytest.raises(AttributeError):
            sdk_utils.getattr_sdk(attr, name)

    def test_expose_func(self):
        @sdk_utils.expose
        def func():
            pass

        assert hasattr(func, '_sdkmeta')

    def test_expose_class(self):
        @sdk_utils.expose
        class some_class():
            pass

        assert hasattr(some_class, '_sdkmetaclass')

    def test_expose_class_functions(self):
        class some_class(object):
            @sdk_utils.expose
            def exposed(self, a, b, c):
                pass

        inst = some_class()

        assert hasattr(getattr(inst, 'exposed'), '_sdkmeta')

    def test_expose_class_mixed(self):
        @sdk_utils.expose
        class some_class(object):
            @sdk_utils.expose
            def exposed(self, a, b, c):
                pass

            def not_exposed(self, a, b, c):
                pass

        inst = some_class()

        assert hasattr(some_class, '_sdkmetaclass')
        assert hasattr(getattr(inst, 'exposed'), '_sdkmeta')
        assert hasattr(getattr(inst, 'not_exposed'), '_sdkmeta') is False
