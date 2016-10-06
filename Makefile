VERSION=$(shell python -c 'import pbr.packaging; print(pbr.packaging.get_version("lago"))')
NAME=lago
TAR_FILE=${NAME}-${VERSION}.tar
TARBALL_FILE=${TAR_FILE}.gz
SPECFILE=${NAME}.spec
# this is needed to use the libs from venv
PYTEST=$(shell which py.test)
FLAKE8=$(shell which flake8)

OUTPUT_DIR=${PWD}
RPM_DIR=${OUTPUT_DIR}/rpmbuild
DIST_DIR=${OUTPUT_DIR}/dist

TAR_DIST_LOCATION=${DIST_DIR}/${TAR_FILE}
TARBALL_DIST_LOCATION=${DIST_DIR}/${TARBALL_FILE}

.PHONY: build rpm srpm ${TARBALL_DIST_LOCATION} check-local dist check ${SPECFILE} docs fullchangelog changelog python-sdist add-extra-files-sdist

changelog:
	echo Creating RPM compatible ChangeLog \
	&& ( \
		scripts/version_manager.py . changelog \
	) > ChangeLog \
	|| ( \
		echo Failed to generate RPM ChangeLog >&2 \
		&& exit 1 \
	)

fullchangelog:
	@if test -d ".git"; then \
		echo Creating FullChangeLog \
		&& ( \
			echo '# Generated by Makefile. Do not edit.'; echo; \
			git log --stat \
		) > FullChangeLog \
		|| ( \
			echo Failed to generate FullChangeLog >&2 \
		); \
	else \
		echo A git clone is required to generate a FullChangeLog >&2; \
	fi

${SPECFILE}: ${SPECFILE}.in changelog
	sed -e "s/@@VERSION@@/${VERSION}/g" \
		${SPECFILE}.in > $@; \
	cat ChangeLog >> $@

build:
	LAGO_VERSION=${VERSION} python setup.py build

check: check-local

check-local:
	@echo "-------------------------------------------------------------"
	@echo "-------------------------------------------------------------"
	@echo "-~      Running style checks                               --"
	@echo "-------------------------------------------------------------"
	scripts/check_style.sh
	@echo "-------------------------------------------------------------"
	@echo "-~      Running static checks                              --"
	@echo "-------------------------------------------------------------"
	PYTHONPATH=${PWD} python ${FLAKE8} --version
	PYTHONPATH=${PWD} python ${FLAKE8}
	@echo "-------------------------------------------------------------"
	@echo "-~      Running unit tests                                 --"
	@echo "-------------------------------------------------------------"
	PYTHONPATH=${PWD} python ${PYTEST} -v tests/unit
	@echo "-------------------------------------------------------------"
	@echo "-------------------------------------------------------------"

dist: ${TARBALL_DIST_LOCATION}

python-sdist:
	LAGO_VERSION=${VERSION} python setup.py sdist --dist-dir ${DIST_DIR}

add-extra-files-sdist: changelog fullchangelog
	gunzip ${TARBALL_DIST_LOCATION}
	tar rvf ${TAR_DIST_LOCATION} \
		FullChangeLog \
		ChangeLog
	gzip ${TAR_DIST_LOCATION}

${TARBALL_DIST_LOCATION}: python-sdist add-extra-files-sdist

srpm: dist ${SPECFILE}
	rpmbuild \
		--define "_topdir ${RPM_DIR}" \
		--define "_sourcedir ${DIST_DIR}" \
		-of \
		${SPECFILE}

rpm: dist ${SPECFILE}
	rpmbuild \
		--define "_topdir ${RPM_DIR}" \
		--define "_sourcedir ${DIST_DIR}" \
		-ba \
		${SPECFILE}

clean:
	python setup.py clean
	rm -rf ${DIST_DIR}
	rm -rf ${RPM_DIR}
	rm -rf build "$(REPO_LOCAL_REL_PATH)"
	rm -f ${SPECFILE}
	rm -f AUTHORS

docs:
	$(MAKE) -C docs clean
	$(MAKE) -C docs html
