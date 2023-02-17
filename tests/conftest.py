# -*- coding: utf-8 -*-
from __future__ import absolute_import
from __future__ import print_function
from __future__ import unicode_literals

import os

import pytest


@pytest.fixture(autouse=True)
def cwd():
    old_dir = os.getcwd()
    os.chdir('/')

    try:
        yield
    finally:
        os.chdir(old_dir)


@pytest.fixture
def venv_path(tmpdir):
    return tmpdir.join('venv')


@pytest.fixture
def activate(venv_path):
    return venv_path.join('.activate.sh')


@pytest.fixture
def deactivate(venv_path):
    return venv_path.join('.deactivate.sh')
