SHELL=bash

.PHONY: test
test:
	tox

.PHONY:	clean
clean:
	rm -rf .tox

.PHONY: builddeb
builddeb:
	mkdir -p dist
	debuild -us -uc -b
	mv ../aactivator_*.deb dist/


# itest / docker build
DOCKER_BUILDER := aactivator-builder-$(USER)
DOCKER_RUN_TEST := docker run -e DEBIAN_FRONTEND=noninteractive -e PIP_INDEX_URL -v $(PWD):/mnt:ro

.PHONY: docker-builder-image
docker-builder-image:
	docker build -t $(DOCKER_BUILDER) .

.PHONY: builddeb-docker
builddeb-docker: docker-builder-image
	mkdir -p dist
	docker run -v $(PWD):/mnt $(DOCKER_BUILDER)

ITEST_TARGETS = itest_bionic itest_focal itest_jammy

.PHONY: itest $(ITEST_TARGETS)
itest: $(ITEST_TARGETS)

itest_bionic: _itest-ubuntu-bionic
itest_focal: _itest-ubuntu-focal
itest_jammy: _itest-ubuntu-jammy

_itest-%: builddeb-docker
	$(DOCKER_RUN_TEST) $(shell sed 's/-/:/' <<< "$*") /mnt/ci/docker
