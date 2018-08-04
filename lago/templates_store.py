import datetime
import json
import logging
import os
import uuid
from functools import partial

from future.builtins import super
from future.utils import raise_from
from sqlalchemy import (
    Column, DateTime, ForeignKey, Integer, String, UniqueConstraint,
    create_engine
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from sqlalchemy.orm.exc import NoResultFound

import utils
from db_utils import BaseMixin, autocommit_safe
from utils import LagoException
import shutil

LOGGER = logging.getLogger(__name__)
Base = declarative_base()


class StoreError(LagoException):
    pass


class RepositoryError(StoreError):
    def __init__(self, repo_name):
        super().__init__('No repository {0} found'.format(repo_name))


class ImageError(StoreError):
    def __init__(self, image):
        super().__init__('No image with hash {0} found'.format(image))


class TagError(StoreError):
    def __init__(self, tag, hash):
        super(
        ).__init__('No tag {0} found for image hash {1}'.format(tag, hash))


class Repository(BaseMixin, Base):
    __tablename__ = 'repositories'
    name = Column(String(256), unique=True)
    repo_type = Column(String(256))
    images = relationship('Image', back_populates='repository')


class Image(BaseMixin, Base):
    __tablename__ = 'images'
    repository_id = Column(Integer, ForeignKey('repositories.id'))
    repository = relationship('Repository', back_populates='images')
    name = Column(String(256))
    creation_date = Column(DateTime)
    hash = Column(String(512), unique=True)
    file = Column(String(1024))
    tags = relationship('ImageTag', back_populates='image')
    __mapper_args__ = {'order_by': creation_date}


class ImageTag(BaseMixin, Base):
    __tablename__ = 'image_tags'
    image_id = Column(Integer, ForeignKey('images.id'))
    image = relationship('Image', back_populates='tags')
    name = Column(String(256))
    __table_args__ = (
        UniqueConstraint('image_id', 'name', name='_image_tag'),
    )
    __mapper_args__ = {'order_by': name}


class ImagesStoreDB(object):
    def __init__(self, uri):
        self._uri = uri
        self._engine = create_engine(uri, echo=False)
        Base.metadata.create_all(self._engine)
        self._sessionmaker = sessionmaker(bind=self._engine)
        self._session = partial(autocommit_safe, self._sessionmaker())

    def add_repo(self, name, repo_type):
        with self._session() as session:
            if self._exists_repo(session, name):
                raise StoreError('Repository {0} already exists'.format(name))
            repo = Repository(name=name, repo_type=repo_type)
            session.add(repo)
        return self.get_repo(name=name)

    def add_tag(self, hash, name):
        with self._session() as session:
            image = self._get_image(session, hash)
            image.tags.append(ImageTag(name=name))
        return self.get_image(hash=hash)

    def add_image(self, name, repo_name, creation_date, hash, file, tags=None):
        with self._session() as session:
            if self._exists_image(session, hash):
                raise StoreError(
                    ('Image with hash {0} already '
                     'exists').format(hash)
                )
            try:
                repo = session.query(Repository).filter(
                    Repository.name == repo_name
                ).one()
            except NoResultFound as exc:
                raise_from(RepositoryError(repo_name), exc)

            image = Image(
                name=name,
                creation_date=creation_date,
                hash=hash,
                file=file,
            )

            if tags is not None:
                for tag in tags:
                    image.tags.append(ImageTag(name=tag))
            repo.images.append(image)

        return self.get_image(hash=hash)

    def delete_tag(self, hash, name):
        with self._session() as session:
            try:
                tag = session.query(ImageTag).join(Image).filter(
                    Image.hash == hash, ImageTag.name == name
                ).one()
            except NoResultFound as exc:
                raise_from(TagError(name, hash), exc)
            session.delete(tag)

    def delete_image(self, hash):
        with self._session() as session:
            image = self._get_image(session, hash)
            session.delete(image)

    def delete_repo(self, name):
        with self._session() as session:
            repo = session.query(Repository).filter(Repository.name == name
                                                    ).one()
            session.delete(repo)

    def list(self, top=10):
        with self._session() as session:
            return [
                row.serialize()
                for row in session.query(Image).limit(top).all()
            ]

    def list_repos(self, top=10):
        with self._session() as session:
            return [
                row.serialize()
                for row in session.query(Repository).limit(top).all()
            ]

    def get_repo(self, name):
        with self._session() as session:
            repo = self._get_repo(session, name)
            return repo.serialize()

    def get_image(self, hash):
        with self._session() as session:
            image = self._get_image(session, hash)
            return image.serialize()

    def get_images_by_name(self, name, repo_name=None):
        filters = [Image.name == name]
        if repo_name is not None:
            filters.append(Repository.name == repo_name)
        with self._session() as session:
            return [
                row.serialize()
                for row in session.query(Image).filter(*filters)
            ]

    def get_images_by_repo(self, repo_name):
        with self._session() as session:
            repo = self._get_repo(session, repo_name)
            return [image.serialize() for image in repo.images]

    def exists_image(self, hash):
        with self._session() as session:
            return self._exists_image(session, hash)

    def exists_repo(self, name):
        with self._session() as session:
            return self._exists_repo(session, name)

    def get_tags(self, hash):
        with self._session() as session:
            image = self._get_image(session, hash)
            return [tag.serialize() for tag in image.tags]

    def reset(self):
        Base.metadata.drop_all(bind=self._engine)
        Base.metadata.create_all(bind=self._engine)

    def _get_image(self, session, hash):
        try:
            image = session.query(Image).filter(Image.hash == hash).one()
            return image
        except NoResultFound as exc:
            raise_from(ImageError(hash), exc)

    def _get_repo(self, session, name):
        try:
            repo = session.query(Repository).filter(Repository.name == name
                                                    ).one()
            return repo
        except NoResultFound as exc:
            raise_from(RepositoryError(name), exc)

    def _exists_repo(self, session, name):
        try:
            self._get_repo(session, name)
            return True
        except RepositoryError:
            return False

    def _exists_image(self, session, hash):
        try:
            self._get_image(session, hash)
            return True
        except ImageError:
            return False


class ImagesStore(object):
    def __init__(self, root, uri=None, tmp_dir=None):
        self._root = os.path.abspath(root)
        if not os.path.isdir(self.root):
            os.makedirs(self.root)
        if uri is None:
            self._uri = 'sqlite:////' + os.path.join(
                self._root, 'store.sqlite'
            )
        else:
            self._uri = uri

        self._db = ImagesStoreDB(uri=self.uri)
        if tmp_dir is None:
            self._tmp_dir = os.path.join(self.root, 'tmp')
            if not os.path.isdir(os.path.join(self.root, 'tmp')):
                os.makedirs(self.tmp_dir)
        else:
            self._tmp_dir = tmp_dir

    def _lock(self, repo):
        return utils.LockFile(
            path=os.path.join(self.root, self.__class__.__name__, repo),
            timeout=180
        )

    @property
    def tmp_dir(self):
        return self._tmp_dir

    @property
    def root(self):
        return self._root

    @property
    def uri(self):
        return self._uri

    def add_repo(self, repo_name, repo_type):
        if self._db.exists_repo(repo_name):
            raise StoreError('Repository {0} already exists'.format(repo_name))
        dst = self._repopath(repo_name)
        if os.path.isdir(dst):
            raise StoreError(
                (
                    'Repository directory {0} exists, but the '
                    'repository is not configured, try removing the '
                    'directory manually.'
                ).format(dst)
            )
        os.makedirs(dst)
        try:
            repo = self._db.add_repo(name=repo_name, repo_type=repo_type)
            LOGGER.debug('added repository %s', repo)
        except:
            shutil.rmtree(dst)
            raise

    def delete_repo(self, repo_name):
        images = self._db.get_images_by_repo(repo_name)
        for image in images:
            self.delete_image(image.hash)
        self._db.delete_repo(repo_name)
        shutil.rmtree(self._repopath(repo_name))

    def add_image(
        self,
        name,
        repo_name,
        hash,
        image_file,
        creation_date,
        metadata,
        tags=None,
        transfer_function=shutil.copy,
    ):
        if not isinstance(creation_date, datetime.date):
            raise StoreError(('creation_date should be a datetime object.'))

        if self._db.exists_image(hash=hash):
            image = self._db.get_image(hash)
            raise StoreError(
                ('Image hash already exists in store: '
                 '{0}').format(image)
            )

        dst = os.path.join(self._repopath(repo_name), uuid.uuid4().hex)
        metadata_dst = self._metafile(dst)
        with self._lock(os.path.dirname(dst)):
            try:
                self._dump_metadata(metadata_dst, metadata, name, repo_name)
                transfer_function(image_file, dst)
                if not os.path.isfile(dst):
                    raise StoreError(
                        ('failed acquiring file {0} to '
                         '{1}').format(image_file, dst)
                    )
                image = self._db.add_image(
                    name=name,
                    repo_name=repo_name,
                    creation_date=creation_date,
                    hash=hash,
                    file=dst,
                    tags=tags
                )
                LOGGER.debug('added to store: %s', image)
                return image
            except:
                utils.safe_unlink(metadata_dst)
                utils.safe_unlink(dst)
                raise

    def delete_image(self, hash):
        image = self._db.get_image(hash)
        with self._lock(os.path.dirname(image.file)):
            self._db.delete_image(hash)
            os.unlink(image.file)
            os.unlink(self._metafile(image.file))
            LOGGER.debug('deleted from store: %s', image)

    def add_tags(self, hash, tags):
        for tag in tags:
            self._db.add_tag(hash, tag)

    def get_image(self, hash):
        return self._db.get_image(hash)

    def get_tags(self, hash):
        return [tag.name for tag in self._db.get_tags(hash)]

    def get_repo(self, name):
        return self._db.get_repo(name)

    def get_images_by_repo(self, repo_name):
        return self._db.get_images_by_repo(repo_name)

    def get_metadata(self, hash):
        image = self._db.get_image(hash)
        with open(self._metafile(image.file)) as meta:
            return json.load(meta)

    def search(self, name, repo_name=None):
        return self._db.get_images_by_name(name, repo_name)

    def exists_repo(self, repo_name):
        return self._db.exists_repo(repo_name)

    def list_images(self, top=10):
        return self._db.list(top)

    def list_repos(self):
        return self._db.list_repos()

    def _metafile(self, dest):
        return dest + '.metadata'

    def _repopath(self, repo_name):
        return os.path.join(self.root, repo_name)

    def _dump_metadata(self, dest, metadata, name, repo_name):
        metadata['store'] = {'name': name, 'repo_name': repo_name}
        with open(dest, 'w') as metafile:
            try:
                utils.json_dump(metadata, metafile)
            except ValueError:
                raise StoreError(
                    (
                        'Unable to serialize metadata, it should be a '
                        'a JSON serializable string: '
                        '{0}.'
                    ).format(metadata)
                )
