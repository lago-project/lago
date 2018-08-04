from pytest import fixture, mark, raises

from lago.templates_store import ImagesStoreDB
from lago.templates_store import RepositoryError, StoreError, ImageError
from collections import namedtuple
import string
from random import choice
from datetime import datetime
Image = namedtuple('Image', 'name, repo_name, creation_date, hash, file, tags')


@fixture
def storedb():
    return ImagesStoreDB(uri='sqlite://')


@fixture
def storedb_with_repo():
    store = ImagesStoreDB(uri='sqlite://')
    store.add_repo(name='default_test_repo', repo_type='unittest')
    return store


@fixture
def repo_stream():
    def gen():
        count = 1
        while True:
            yield ('repo{0}'.format(count), 'type{0}'.format(count))
            count = count + 1

    return gen()


def random_str(length=20):
    return u''.join(choice(string.ascii_letters) for _ in range(20))


def generate_image(**kwargs):
    return Image(
        name=kwargs.get('name', random_str()),
        repo_name=kwargs.get('repo_name', random_str()),
        creation_date=kwargs.get('creation_date', datetime.now()),
        hash=kwargs.get('hash', 'hash' + random_str()),
        file=kwargs.get('file', random_str()),
        tags=kwargs.get('tags', [])
    )


def assert_images(result, image):
    assert result.name == image.name
    assert result.creation_date == image.creation_date
    assert result.hash == image.hash
    assert result.file == image.file


# @fixture
# def images_stream():
# def gen()


class TestImageStoreDB(object):
    @mark.parametrize('number_of_repos', range(1, 5))
    def test_add_repo(self, storedb, repo_stream, number_of_repos):
        # TO-DO: refactor to reduce some code
        repos = [next(repo_stream) for _ in range(number_of_repos)]
        for repo in repos:
            result = storedb.add_repo(*repo)
            assert result.name == repo[0]
            assert result.repo_type == repo[1]
            assert storedb.exists_repo(name=repo[0]) == True
        for repo in repos:
            with raises(StoreError):
                result = storedb.add_repo(*repo)

        new_repos = [next(repo_stream) for _ in range(2)]
        for repo in new_repos:
            result = storedb.add_repo(*repo)
            assert result.name == repo[0]
            assert result.repo_type == repo[1]
            assert storedb.exists_repo(name=repo[0]) == True

        for repo in new_repos:
            with raises(StoreError):
                result = storedb.add_repo(*repo)

    def test_add_image_no_repo(self, storedb):
        image = generate_image()
        with raises(RepositoryError):
            storedb.add_image(**image._asdict())

    def test_add_image_simple(self, storedb_with_repo):
        repo_name = storedb_with_repo.list_repos()[0].name
        image = generate_image(repo_name=repo_name)
        result = storedb_with_repo.add_image(**image._asdict())
        assert_images(result, image)
        assert result.repository_id == storedb_with_repo.get_repo(repo_name).id

    def test_add_image_no_duplicate_hash(self, storedb_with_repo):
        repo_name = storedb_with_repo.list_repos()[0].name
        image = generate_image(repo_name=repo_name)
        result = storedb_with_repo.add_image(**image._asdict())
        assert_images(result, image)
        assert result.repository_id == storedb_with_repo.get_repo(repo_name).id
        with raises(StoreError):
            storedb_with_repo.add_image(
                **generate_image(hash=image.hash)._asdict()
            )

    def test_retrive_image(self, storedb_with_repo):
        repo_name = storedb_with_repo.list_repos()[0].name
        image = generate_image(repo_name=repo_name)
        storedb_with_repo.add_image(**image._asdict())
        result = storedb_with_repo.get_image(image.hash)
        assert_images(result, image)
        results = storedb_with_repo.get_image_by_name(image.name)
        assert len(results) == 1
        assert_images(results[0], image)
