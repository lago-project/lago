_DESCRIBE=$(shell git describe --tags)
VERSION=$(shell echo $(_DESCRIBE) | sed 's/-.*//')
RELEASE=$(shell echo $(_DESCRIBE) | sed 's/^[^-]*-//' | tr '-' '_')
NAME=lago
FULL_NAME=${NAME}-${VERSION}
TAR_FILE=${FULL_NAME}.tar
TARBALL_FILE=${TAR_FILE}.gz
SPECFILE=lago.spec

OUTPUT_DIR=${PWD}
RPM_DIR=${OUTPUT_DIR}/rpmbuild
DIST_DIR=${OUTPUT_DIR}/dist

REPO_SSH_USER=dimak
REPO_SSH_HOST=fedorapeople.org
REPO_SSH_REMOTE_REL_PATH="public_html/lago"
REPO_LOCAL_REL_PATH="repo"

TAR_DIST_LOCATION=${DIST_DIR}/${TAR_FILE}
TARBALL_DIST_LOCATION=${DIST_DIR}/${TARBALL_FILE}

.PHONY: build rpm srpm ${TARBALL_DIST_LOCATION} check-local dist check repo upload upload-unstable ${SPECFILE} docs

${SPECFILE}: ${SPECFILE}.in
	sed \
		-e s/@VERSION@/${VERSION}/g \
		-e s/@RELEASE@/${RELEASE}/g \
		$< > $@

build:
	LAGO_VERSION=${VERSION} python setup.py build

check: check-local

check-local:
	@echo "-------------------------------------------------------------"
	@echo "-------------------------------------------------------------"
	@echo "-~      Running static checks                              --"
	@echo "-------------------------------------------------------------"
	find . -name '*.py' | xargs flake8
	@echo "-------------------------------------------------------------"
	@echo "-~      Running unit tests                                 --"
	@echo "-------------------------------------------------------------"
	PYTHONPATH=${PWD}/lib:${PYTHONPATH} nosetests -v tests/*.py
	@echo "-------------------------------------------------------------"
	@echo "-------------------------------------------------------------"

dist: ${TARBALL_DIST_LOCATION}

${TARBALL_DIST_LOCATION}:
	LAGO_VERSION=${VERSION} python setup.py sdist --dist-dir ${DIST_DIR}
	gunzip ${TARBALL_DIST_LOCATION}
	tar rvf ${TAR_DIST_LOCATION} \
		bin \
		contrib \
		etc \
		scripts \
		sudo \
		polkit
	gzip ${TAR_DIST_LOCATION}

srpm: ${SPECFILE} dist
	rpmbuild 					\
		--define "_topdir ${RPM_DIR}" 	\
		--define "_sourcedir ${DIST_DIR}" 	\
		-bs 					\
		${SPECFILE}

rpm: ${SPECFILE} dist
	rpmbuild 					\
		--define "_topdir ${RPM_DIR}" 	\
		--define "_sourcedir ${DIST_DIR}" 	\
		-ba 					\
		${SPECFILE}

repo: rpm
	rm -rf "${REPO_LOCAL_REL_PATH}/"
	mkdir "${REPO_LOCAL_REL_PATH}"
	find ${RPM_DIR} -name '*$(VERSION)-$(RELEASE)*.rpm' -exec cp '{}' "${REPO_LOCAL_REL_PATH}/" \;
	cd "${REPO_LOCAL_REL_PATH}/"
	createrepo "${REPO_LOCAL_REL_PATH}/"
	cp "${TAR_DIST_LOCATION}" "${SPECFILE}"  "${REPO_LOCAL_REL_PATH}/"

upload: repo
	ssh "${REPO_SSH_USER}@${REPO_SSH_HOST}" "rm -rf ${REPO_SSH_REMOTE_REL_PATH}/*"
	scp -r "${REPO_LOCAL_REL_PATH}/*" "${REPO_SSH_USER}@${REPO_SSH_HOST}":"${REPO_SSH_REMOTE_REL_PATH}"

upload-unstable: repo
	ssh "${REPO_SSH_USER}@${REPO_SSH_HOST}" "rm -rf ${REPO_SSH_REMOTE_REL_PATH}-unstable/*"
	scp -r "${REPO_LOCAL_REL_PATH}/*" "${REPO_SSH_USER}@${REPO_SSH_HOST}":"${REPO_SSH_REMOTE_REL_PATH}-unstable"

clean:
	LAGO_VERSION=${VERSION} python setup.py clean
	rm -rf ${DIST_DIR}
	rm -rf ${RPM_DIR}
	rm -rf build "$(REPO_LOCAL_REL_PATH)"
	rm -f ${SPECFILE}

docs:
	$(MAKE) -C docs clean
	$(MAKE) -C docs html
