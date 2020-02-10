from __future__ import absolute_import

import pytest
import logging
from lago import sdk


class TestSDK(object):
    @pytest.mark.parametrize('level', ['INFO', 'CRITICAL', 'DEBUG'])
    @pytest.mark.parametrize('name', ['logger1', 'l2'])
    @pytest.mark.parametrize('msg', ['m1', 'm2', 'a b'])
    def test_add_stream_logger(self, caplog, level, name, msg):
        sdk.add_stream_logger(level=level, name=name)
        logger = logging.getLogger(name)
        assert logger.getEffectiveLevel() == getattr(logging, level)
        log_at_level = getattr(logger, level.lower())
        log_at_level(msg)
        assert caplog.record_tuples == [
            (name, getattr(logging, level.upper()), msg),
        ]

    @pytest.mark.parametrize('level', ['INFO', 'CRITICAL', 'DEBUG'])
    def test_init_logger_new_env(
        self, tmpdir, monkeypatch, mock_workdir, empty_prefix, level
    ):
        log_path = tmpdir.mkdir('logs').join('test.log')
        monkeypatch.setattr(
            'lago.cmd.do_init', lambda **kwargs: (mock_workdir, empty_prefix)
        )
        sdk.init(
            config=None, workdir=None, logfile=str(log_path), loglevel=level
        )
        handlers = [
            h for h in logging.root.handlers
            if isinstance(h, logging.FileHandler)
        ]
        assert len(handlers) == 1
        handler = handlers.pop()
        assert handler.stream.name == str(log_path)
        assert handler.level == getattr(logging, level)

        logging.root.removeHandler(handler)

    @pytest.mark.parametrize('level', ['INFO', 'CRITICAL', 'DEBUG'])
    def test_init_logger_loaded_env(
        self, tmpdir, monkeypatch, mock_workdir, empty_prefix, level
    ):
        log_path = tmpdir.mkdir('logs').join('test.log')
        monkeypatch.setattr(
            'lago.workdir.Workdir.get_prefix', lambda *args, **kwargs:
            empty_prefix
        )
        sdk.load_env(
            workdir=str(tmpdir), logfile=str(log_path), loglevel=level
        )
        handlers = [
            h for h in logging.root.handlers
            if isinstance(h, logging.FileHandler)
        ]
        assert len(handlers) == 1
        handler = handlers.pop()
        assert handler.stream.name == str(log_path)
        assert handler.level == getattr(logging, level)

        logging.root.removeHandler(handler)
