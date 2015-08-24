_DESCRIBE=$(shell git describe --tags)
VERSION=$(shell echo $(_DESCRIBE) | sed 's/-.*//')
RELEASE=$(shell echo $(_DESCRIBE) | sed 's/^[^-]*-//' | tr '-' '_')
NAME=testenv
FULL_NAME=${NAME}-${VERSION}
TAR_FILE=${FULL_NAME}.tar.gz

SPECFILE=testenv.spec

OUTPUT_DIR=${PWD}
RPM_DIR=${OUTPUT_DIR}/rpmbuild
DIST_DIR=${OUTPUT_DIR}/dist

TAR_DIST_LOCATION=${DIST_DIR}/${TAR_FILE}

.PHONY: build rpm srpm ${TAR_DIST_LOCATION} check-local dist check repo upload upload-unstable ${SPECFILE}

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

dist: ${TAR_DIST_LOCATION}

${TAR_DIST_LOCATION}:
	TESTENV_VERSION=${VERSION} python setup.py sdist --dist-dir ${DIST_DIR}

srpm: ${SPECFILE} ${TAR_DIST_LOCATION} dist
	rpmbuild 					\
		--define "_topdir ${RPM_DIR}" 	\
		--define "_sourcedir ${DIST_DIR}" 	\
		-bs 					\
		${SPECFILE}

rpm: ${SPECFILE} ${TAR_DIST_LOCATION} dist
	rpmbuild 					\
		--define "_topdir ${RPM_DIR}" 	\
		--define "_sourcedir ${DIST_DIR}" 	\
		-ba 					\
		${SPECFILE}

repo: dist rpm
	rm -rf repo/
	mkdir repo
	find ${RPM_DIR} -name '*$(VERSION)-$(RELEASE)*.rpm' -exec cp '{}' repo/ \;
	cd repo/
	createrepo repo/
	cp ${TAR_DIST_LOCATION} ${SPECFILE} repo/

upload: repo
	ssh dimak@fedorapeople.org 'rm -rf public_html/testenv/*'
	scp -r repo/* dimak@fedorapeople.org:public_html/testenv

upload-unstable: repo
	ssh dimak@fedorapeople.org 'rm -rf public_html/testenv-unstable/*'
	scp -r repo/* dimak@fedorapeople.org:public_html/testenv-unstable

clean:
	TESTENV_VERSION=${VERSION} python setup.py clean
	rm -rf ${DIST_DIR}
	rm -rf ${RPM_DIR}
	rm -rf build repo
	rm -f ${SPECFILE}

