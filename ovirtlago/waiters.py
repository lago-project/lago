import time

import pkg_resources
import yaml

from ovirtsdk4 import types as ovirt_types


class WaiterError(BaseException):
    pass


class Waiter(object):
    def __init__(self, config):
        self.config = config
        self.state = 'unknown'
        self.name = config['waiter_name']
        self.rejectors = self._build_matchers(config.get('rejectors', []))
        self.acceptors = self._build_matchers(config['acceptors'])
        self.target = self.config['target']['name']
        self.target_path = self.config['target']['path']
        self.operation = self._build_operation()

    # TO-DO: create a matcher class which holds more details about
    # the result.

    def _build_matchers(self, matchers):
        callables = []
        for matcher in matchers:
            if matcher['type'] == 'status':
                callables.append(self._build_status_matcher(matcher))
        return callables

    def _build_status_matcher(self, matcher):
        def exact_match(result):
            base = (
                getattr(getattr(ovirt_types, matcher['name']), path)
                for path in matcher['paths']
            )
            return result.status in base

        return exact_match

    def _build_operation(self):
        def func(api, *args, **kwargs):
            system_service = getattr(api, 'system_service')()
            service = getattr(system_service, self.config['service'])()
            target = getattr(service, self.target)(*args, **kwargs)
            return getattr(target, self.target_path)()

        return func

    def wait(self, api, *args, **kwargs):
        max_attempts = kwargs.pop('max_attempts',
                                  False) or self.config['max_attempts']
        delay = kwargs.pop('delay', False) or self.config['delay']
        attempts = 0
        max_attempts = int(max_attempts)
        delay = int(delay)

        while True:
            res = self.operation(api, *args, **kwargs)
            attempts = attempts + 1
            for acceptor in self.acceptors:
                if acceptor(res):
                    self.state = 'success'
                    break

            for rejector in self.rejectors:
                if rejector(res):
                    self.state = 'failed'
                    raise WaiterError('rejected state')

            if self.state == 'success':
                return

            if attempts >= max_attempts:
                raise WaiterError('Maximum number of attempts exceeded')
            time.sleep(delay)


class _waiters_meta(type):
    def __init__(self, name, bases, d):
        type.__init__(self, name, bases, d)
        config = pkg_resources.resource_filename(
            __name__, '/'.join(['data', 'waiters.yaml'])
        )
        with open(config, 'r') as waiters_fd:
            waiters_cfg = yaml.load(waiters_fd)['waiters']

        for waiter_cfg in waiters_cfg:
            waiter = Waiter(config=waiter_cfg)
            # TO-DO: attach docstring for the wait method
            # according to the waiter name
            setattr(self, waiter.name, waiter.wait)


class waiters:
    __metaclass__ = _waiters_meta
    pass
