_DESCRIBE=$(shell git describe --tags)
VERSION=$(shell echo $(_DESCRIBE) | sed 's/-.*//')
RELEASE=$(shell echo $(_DESCRIBE) | sed 's/^[^-]*-//' | tr '-' '_')
NAME=testenv
FULL_NAME=${NAME}-${VERSION}
TAR_FILE=${FULL_NAME}.tar.gz

SPECFILE=testenv.spec

DIST=dist
TAR_DIST_LOCATION=${DIST}/${TAR_FILE}

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

dist: check ${TAR_DIST_LOCATION}

${TAR_DIST_LOCATION}:
	TESTENV_VERSION=${VERSION} python setup.py sdist

srpm: ${SPECFILE} ${TAR_DIST_LOCATION} dist
	rpmbuild 					\
		--define "_topdir `pwd`/rpmbuild" 	\
		--define "_sourcedir `pwd`/${DIST}" 	\
		-bs 					\
		${SPECFILE}

rpm: ${SPECFILE} ${TAR_DIST_LOCATION} dist
	rpmbuild 					\
		--define "_topdir `pwd`/rpmbuild" 	\
		--define "_sourcedir `pwd`/${DIST}"	\
		-ba 					\
		${SPECFILE}

repo: dist rpm
	rm -rf repo/
	mkdir repo
	find rpmbuild/ -name '*$(VERSION)-$(RELEASE)*.rpm' -exec cp '{}' repo/ \;
	cd repo/
	createrepo repo/
	cp dist/testenv-${VERSION}.tar.gz ${SPECFILE} repo/

upload: repo
	ssh dimak@fedorapeople.org 'rm -rf public_html/testenv/*'
	scp -r repo/* dimak@fedorapeople.org:public_html/testenv

upload-unstable: repo
	ssh dimak@fedorapeople.org 'rm -rf public_html/testenv-unstable/*'
	scp -r repo/* dimak@fedorapeople.org:public_html/testenv-unstable

clean:
	TESTENV_VERSION=${VERSION} python setup.py clean
	rm -rf ${DIST}
	rm -rf build dist repo rpmbuild
	rm -f ${SPECFILE}

