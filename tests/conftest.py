# -*- coding: utf-8 -*-
from __future__ import absolute_import
from __future__ import print_function
from __future__ import unicode_literals

import pytest
from py._path.local import LocalPath


@pytest.fixture(autouse=True)
def cwd():
    with LocalPath('/').as_cwd():
        yield


@pytest.fixture
def venv_path(tmpdir):
    return tmpdir.join('venv')


@pytest.fixture
def activate(venv_path):
    return venv_path.join('.activate.sh')


@pytest.fixture
def deactivate(venv_path):
    return venv_path.join('.deactivate.sh')
