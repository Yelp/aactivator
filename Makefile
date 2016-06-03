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
TEST_PACKAGE_DEPS := bash build-essential ca-certificates curl python2.7 python2.7-dev python-setuptools sudo zsh
DOCKER_BUILDER := aactivator-builder-$(USER)

# XXX: We must put /tmp on a volume (and then chmod it), or the filesystem
# reports a different device ("filesystem ID") for files than directories,
# which breaks our path safety checks. Probably due to AUFS layering?
DOCKER_RUN_TEST := docker run -e DEBIAN_FRONTEND=noninteractive -v /tmp -v $(PWD):/mnt:ro
DOCKER_TEST_CMD := sh -euxc '\
	chmod 1777 /tmp \
	&& apt-get update \
	&& (grep -vqE "\blucid\b" /etc/apt/sources.list || ( \
		apt-get install -y --no-install-recommends python-software-properties \
		&& echo "Adding frull/deadsnakes for lucid Python 2.7 backport" \
		&& add-apt-repository ppa:fkrull/deadsnakes \
		&& echo "Adding blueyed/ppa for lucid zsh backport" \
		&& add-apt-repository ppa:blueyed/ppa \
		&& apt-get update \
	)) \
	&& apt-get install -y --no-install-recommends $(TEST_PACKAGE_DEPS) \
	&& curl https://bootstrap.pypa.io/get-pip.py | python2.7 \
	&& dpkg -i /mnt/dist/*.deb \
	&& pip install -r /mnt/requirements-dev.txt \
	&& pip install /mnt \
	&& cp -r /mnt /tmp/test \
	&& py.test -vv /tmp/test'

.PHONY: docker-builder-image
docker-builder-image:
	docker build -t $(DOCKER_BUILDER) .

.PHONY: builddeb-docker
builddeb-docker: docker-builder-image
	mkdir -p dist
	docker run -v $(PWD):/mnt $(DOCKER_BUILDER)

ITEST_TARGETS = itest_lucid itest_precise itest_trusty itest_xenial itest_wheezy itest_jessie itest_stretch

.PHONY: itest $(ITEST_TARGETS)
itest: $(ITEST_TARGETS)

itest_lucid: _itest-ubuntu-lucid
itest_precise: _itest-ubuntu-precise
itest_trusty: _itest-ubuntu-trusty
itest_xenial: _itest-ubuntu-xenial
itest_wheezy: _itest-debian-wheezy
itest_jessie: _itest-debian-jessie
itest_stretch: _itest-debian-stretch

_itest-%: builddeb-docker
	$(DOCKER_RUN_TEST) $(shell sed 's/-/:/' <<< "$*") $(DOCKER_TEST_CMD)
