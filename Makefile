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

ITEST_TARGETS = itest_focal itest_jammy

.PHONY: itest
itest: $(ITEST_TARGETS)

.PHONY: itest_%
itest_%: builddeb-docker
	$(DOCKER_RUN_TEST) ubuntu:$* /mnt/ci/docker
