BASE_PATH=el7-systemd
LIBVIRT_PATH=el7-systemd-libvirt
BASE_CONTAINER_NAME=el7-systemd
LIBVIRT_CONTAINER_NAME=el7-systemd-libvirt

.PHONY: base-container libvirt-container lago-container

lago-container: libvirt-container
	./build-lago-container.sh \
		${RPM_PATH} \
		${LIBVIRT_CONTAINER_NAME} \
		el7-systemd-lago

libvirt-container: base-container
	sed "s/@BASE@/${BASE_CONTAINER_NAME}/g" \
		< ${LIBVIRT_PATH}/Dockerfile.in \
		> ${LIBVIRT_PATH}/Dockerfile

	docker build \
		-t ${LIBVIRT_CONTAINER_NAME} \
		${LIBVIRT_PATH}

base-container:
	docker build -t ${BASE_CONTAINER_NAME} el7-systemd

