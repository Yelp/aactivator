SHELL=bash

.PHONY: test
test:
	tox

.PHONY: builddeb
builddeb:
	mkdir -p dist
	debuild -us -uc -b
	mv ../aactivator_*.deb dist/


# itest / docker build
DOCKER_BUILDER := aactivator-builder-$(USER)

# XXX: We must put /tmp on a volume (and then chmod it), or the filesystem
# reports a different device ("filesystem ID") for files than directories,
# which breaks our path safety checks. Probably due to AUFS layering?
DOCKER_RUN_TEST := docker run -e DEBIAN_FRONTEND=noninteractive -v /tmp -v $(PWD):/mnt:ro

.PHONY: docker-builder-image
docker-builder-image:
	docker build -t $(DOCKER_BUILDER) .

.PHONY: builddeb-docker
builddeb-docker: docker-builder-image
	mkdir -p dist
	docker run -v $(PWD):/mnt $(DOCKER_BUILDER)

ITEST_TARGETS = itest_xenial itest_bionic itest_stretch itest_buster

.PHONY: itest $(ITEST_TARGETS)
itest: $(ITEST_TARGETS)

itest_xenial: _itest-ubuntu-xenial
itest_bionic: _itest-ubuntu-bionic
itest_stretch: _itest-debian-stretch
itest_buster: _itest-debian-buster

_itest-%: builddeb-docker
	$(DOCKER_RUN_TEST) $(shell sed 's/-/:/' <<< "$*") /mnt/ci/docker
