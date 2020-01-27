from __future__ import print_function

from lago import utils
from lago.log_utils import LogTask
import pytest


class LoggerMock(object):
    def debug(self, msg):
        print(msg)

    def info(self, msg):
        print(msg)


class TestLogUtils(object):
    @pytest.fixture(scope='class')
    def logger(self):
        return LoggerMock()

    def thrower(self, logger):
        with LogTask('I should throw the exception', logger=logger):
            raise RuntimeError()

    def catcher(self, logger):
        with LogTask('I should catch the exception', logger=logger):
            try:
                raise RuntimeError()
            except RuntimeError:
                pass

    def test_log_task(self, logger):
        def check_raises():
            with pytest.raises(RuntimeError):
                self.thrower(logger)

        def check_catches():
            try:
                self.catcher(logger)
            except RuntimeError:
                pytest.fail('function "catch" did not catch the exception')

        utils.invoke_different_funcs_in_parallel(check_raises, check_catches)
