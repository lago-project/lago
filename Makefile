VERSION=0.2
RELEASE=5
NAME=testenv
FULL_NAME=${NAME}-${VERSION}
TAR_FILE=${FULL_NAME}.tar.gz

SPECFILE=testenv.spec

DIST=dist
TAR_DIST_LOCATION=${DIST}/${TAR_FILE}

.PHONY: build rpm srpm ${TAR_DIST_LOCATION} check-local dist check

${SPECFILE}: ${SPECFILE}.in
	sed \
		-e s/@VERSION@/${VERSION}/g \
		-e s/@RELEASE@/${RELEASE}/g \
		$< > $@

build:
	TESTENV_VERSION=${VERSION} python setup.py build

check: check-local

check-local:
	find . -name '*.py' | xargs flake8
	PYTHONPATH=${PWD}/lib:${PYTHONPATH} nosetests -v tests/*.py

dist: check ${TAR_DIST_LOCATION}

${TAR_DIST_LOCATION}:
	TESTENV_VERSION=${VERSION} python setup.py sdist

srpm: ${SPECFILE} ${TAR_DIST_LOCATION} dist
	rpmbuild --define "_sourcedir `pwd`/${DIST}" -bs ${SPECFILE}

rpm: ${SPECFILE} ${TAR_DIST_LOCATION} dist
	rpmbuild --define "_sourcedir `pwd`/${DIST}" -ba ${SPECFILE}

clean:
	TESTENV_VERSION=${VERSION} python setup.py clean
	rm -rf ${DIST}
	rm -rf build
	rm -f ${SPECFILE}
