# -*- coding: utf-8 -*-
from __future__ import absolute_import
from __future__ import print_function
from __future__ import unicode_literals

import functools
import sys

import pytest

import aactivator
from testing import make_venv_in_tempdir


@pytest.fixture
def f_path(tmpdir):
    return tmpdir.join('f')


@pytest.fixture
def inactive_env(tmpdir):
    return (
        ('HOME', str(tmpdir)),
        ('AACTIVATOR_VERSION', aactivator.__version__),
    )


@pytest.fixture
def allowed_config(tmpdir):
    return tmpdir.join('.cache/aactivator/allowed')


@pytest.fixture
def disallowed_config(tmpdir):
    return tmpdir.join('.cache/aactivator/disallowed')


@pytest.fixture
def active_env(venv_path, inactive_env):
    return inactive_env + (('AACTIVATOR_ACTIVE', str(venv_path)),)


def test_is_safe_to_source_fine(f_path):
    f_path.open('a').close()
    assert aactivator.insecure(str(f_path)) is None


def test_is_safe_to_source_not_fine(f_path):
    f_path.open('a').close()
    f_path.chmod(0o666)
    assert aactivator.insecure(str(f_path)) == str(f_path)


def test_is_safe_to_source_also_not_fine(f_path):
    f_path.open('a').close()
    f_path.chmod(0o777)
    assert aactivator.insecure(str(f_path)) == str(f_path)


def test_directory_writeable_not_fine(tmpdir, f_path):
    f_path.open('a').close()
    tmpdir.chmod(0o777)
    assert aactivator.insecure(str(f_path)) == str(tmpdir)


def test_security_check_for_path_non_sourceable(tmpdir, f_path):
    f_path.open('a').close()
    f_path.chmod(0o666)
    with tmpdir.as_cwd():
        assert (
            aactivator.security_check(str(f_path)) ==
            'aactivator: Cowardly refusing to source f because writeable by others: f'
        )


def test_security_check_for_path_sourceable(f_path):
    f_path.open('a').close()
    assert aactivator.security_check(str(f_path)) is None


def test_security_check_for_path_nonexistant(f_path):
    assert (
        aactivator.security_check(str(f_path)) ==
        'aactivator: File does not exist: ' + str(f_path)
    )


def test_get_output_nothing_special(tmpdir, inactive_env):
    output = aactivator.get_output(
        dict(inactive_env),
        str(tmpdir),
    )
    assert output == ''


def test_get_output_already_sourced(tmpdir, venv_path, active_env):
    make_venv_in_tempdir(tmpdir)
    output = aactivator.get_output(
        dict(active_env),
        str(venv_path),
        lambda: 'y',
    )
    assert output == ''


def test_get_output_sourced_not_in_directory(tmpdir, venv_path, active_env):
    make_venv_in_tempdir(tmpdir)
    output = aactivator.get_output(
        dict(active_env),
        str(tmpdir),
    )
    assert (
        output ==
        '''\
OLDPWD_bak="$OLDPWD" &&
cd {venv_path} &&
aactivator security-check .deactivate.sh &&
source ./.deactivate.sh
unset AACTIVATOR_ACTIVE &&
cd "$OLDPWD_bak" &&
cd {tmpdir} &&
unset OLDPWD_bak'''.format(venv_path=str(venv_path), tmpdir=str(tmpdir))
    )


def test_get_output_sourced_deeper_in_directory(tmpdir, venv_path, active_env):
    make_venv_in_tempdir(tmpdir)
    deeper = venv_path.mkdir('deeper')

    output = aactivator.get_output(
        dict(active_env),
        str(deeper),
        lambda: 'y',
    )
    assert output == ''


def test_get_output_sourced_deeper_venv(tmpdir, venv_path, active_env):
    make_venv_in_tempdir(tmpdir)
    deeper = make_venv_in_tempdir(venv_path, 'deeper')

    output = aactivator.get_output(
        dict(active_env),
        str(deeper),
        lambda: 'y',
    )
    assert (
        output ==
        '''\
OLDPWD_bak="$OLDPWD" &&
cd {venv_path} &&
aactivator security-check .deactivate.sh &&
source ./.deactivate.sh
unset AACTIVATOR_ACTIVE &&
cd "$OLDPWD_bak" &&
cd {venv_path}/deeper &&
unset OLDPWD_bak &&
aactivator security-check .activate.sh &&
source ./.activate.sh &&
export AACTIVATOR_ACTIVE={venv_path}/deeper'''.format(venv_path=str(venv_path))
    )


def test_not_sourced_sources(tmpdir, venv_path, inactive_env):
    make_venv_in_tempdir(tmpdir)
    output = aactivator.get_output(
        dict(inactive_env),
        str(venv_path),
        lambda: 'y',
    )
    assert (
        output ==
        '''\
aactivator security-check .activate.sh &&
source ./.activate.sh &&
export AACTIVATOR_ACTIVE=''' + str(venv_path)
    )


def test_get_output_change_venv(tmpdir, venv_path, active_env):
    make_venv_in_tempdir(tmpdir)
    venv2 = make_venv_in_tempdir(tmpdir, 'venv2')
    output = aactivator.get_output(
        dict(active_env),
        str(venv2),
        lambda: 'y',
    )
    assert (
        output ==
        '''\
OLDPWD_bak="$OLDPWD" &&
cd {venv_path} &&
aactivator security-check .deactivate.sh &&
source ./.deactivate.sh
unset AACTIVATOR_ACTIVE &&
cd "$OLDPWD_bak" &&
cd {venv_path}2 &&
unset OLDPWD_bak &&
aactivator security-check .activate.sh &&
source ./.activate.sh &&
export AACTIVATOR_ACTIVE={venv_path}2'''.format(venv_path=str(venv_path))
    )


def test_get_output_pwd_goes_missing(tmpdir, venv_path, inactive_env):
    make_venv_in_tempdir(tmpdir)
    with venv_path.as_cwd():
        venv_path.remove(rec=1)
        output = aactivator.get_output(
            dict(inactive_env),
            str(venv_path),
            lambda: 'n',
        )
    assert output == ''


def config(inactive_env, answer):
    return aactivator.ActivateConfig(
        dict(inactive_env),
        lambda: print(answer, file=sys.stderr) or answer,
    )


@pytest.fixture
def yes_config(inactive_env):
    return lambda: config(inactive_env, 'y')


@pytest.fixture
def no_config(inactive_env):
    return lambda: config(inactive_env, 'n')


@pytest.fixture
def never_config(inactive_env):
    return lambda: config(inactive_env, 'N')


@pytest.fixture
def eof_config(inactive_env):
    def raise_eoferror():
        raise EOFError()
    return functools.partial(
        aactivator.ActivateConfig,
        dict(inactive_env),
        raise_eoferror,
    )


def test_prompt_loop_answer_yes(tmpdir, venv_path, yes_config, allowed_config):
    make_venv_in_tempdir(tmpdir)
    assert yes_config().find_allowed(str(venv_path)) == str(venv_path)
    assert allowed_config.check(file=1)
    assert allowed_config.read() == venv_path + '\n'


def test_no_config_not_allowed(tmpdir, venv_path, no_config, allowed_config, disallowed_config):
    make_venv_in_tempdir(tmpdir)
    assert no_config().find_allowed(str(venv_path)) is None
    # Saying no should not permanently save anything
    assert allowed_config.check(exists=0)
    assert disallowed_config.check(exists=0)


def test_eof_treated_like_no(tmpdir, venv_path, eof_config, allowed_config, disallowed_config):
    make_venv_in_tempdir(tmpdir)
    assert eof_config().find_allowed(str(venv_path)) is None
    # Saying no should not permanently save anything
    assert allowed_config.check(exists=0)
    assert disallowed_config.check(exists=0)


def test_never_config_not_allowed(tmpdir, venv_path, never_config, allowed_config, disallowed_config):
    make_venv_in_tempdir(tmpdir)
    assert never_config().find_allowed(str(venv_path)) is None
    assert disallowed_config.check(file=1)
    assert disallowed_config.read() == str(venv_path) + '\n'


def test_yes_config_is_remembered(tmpdir, venv_path, yes_config, no_config):
    make_venv_in_tempdir(tmpdir)
    assert yes_config().find_allowed(str(venv_path)) == str(venv_path)
    assert no_config().find_allowed(str(venv_path)) == str(venv_path)


def test_never_is_remembered(tmpdir, venv_path, never_config, yes_config):
    make_venv_in_tempdir(tmpdir)
    assert never_config().find_allowed(str(venv_path)) is None
    assert yes_config().find_allowed(str(venv_path)) is None


def test_not_owned_by_me_is_not_activatable(tmpdir, activate, yes_config):
    make_venv_in_tempdir(tmpdir)
    assert yes_config().is_allowed(str(activate), _getuid=lambda: -1) is False


def test_no_is_remembered_until_cd_out(venv_path, tmpdir, no_config, yes_config):
    venv = make_venv_in_tempdir(tmpdir)
    assert no_config().find_allowed(str(venv_path)) is None
    assert yes_config().find_allowed(str(venv_path)) is None

    # cd to a child directory shouldn't forget the answer
    child_dir = venv.join('child-dir')
    assert yes_config().find_allowed(str(child_dir)) is None

    # cd to a parent directory directory (and back) should
    assert yes_config().find_allowed('/') is None
    assert yes_config().find_allowed(str(child_dir)) == str(venv_path)
