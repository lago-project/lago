from contextlib import contextmanager
from collections import namedtuple
from sqlalchemy.sql import func
from sqlalchemy import (Column, DateTime, Integer)


def autorepr(self):
    cols = (str(col.key) for col in self.__table__.columns)
    key_values = ('{0}="{1}"'.format(col, getattr(self, col)) for col in cols)
    return '<{0}({1})>'.format(self.__class__.name, ','.join(key_values))


@contextmanager
def autocommit_safe(session):
    try:
        yield session
        session.commit()
    except:
        session.rollback()
        raise


def namedtuple_serialize(self):
    cols = ','.join([str(col.key) for col in self.__table__.columns])
    record = namedtuple(self.__class__.__name__, cols)
    return record._make(
        [getattr(self, col.key) for col in self.__table__.columns]
    )


class BaseMixin(object):
    id = Column(Integer, primary_key=True)
    add_date = Column(DateTime, server_default=func.now())
    __repr__ = autorepr

    def serialize(self):
        return namedtuple_serialize(self)
