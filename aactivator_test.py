# -*- coding: utf-8 -*-
from __future__ import absolute_import
from __future__ import print_function
from __future__ import unicode_literals

import functools
import os.path
import re
import sys

import pexpect
import pytest

import aactivator


def make_venv_in_tempdir(tmpdir, name='venv'):
    venv = tmpdir.mkdir(name)
    venv.mkdir('child-dir')
    venv.join('banner').write('aactivating...\n')
    venv.join('.activate.sh').write('''\
cat banner
alias echo='echo "(aliased)"'
''')
    venv.join('.deactivate.sh').write('echo deactivating...\nunalias echo\n')
    return venv


@pytest.yield_fixture(autouse=True)
def cwd():
    olddir = os.getcwd()
    os.chdir('/')
    yield
    os.chdir(olddir)


@pytest.fixture
def venv_path(tmpdir):
    return tmpdir.join('venv')


@pytest.fixture
def activate(venv_path):
    return venv_path.join('.activate.sh')


@pytest.fixture
def deactivate(venv_path):
    return venv_path.join('.deactivate.sh')


@pytest.fixture
def allowed_config(tmpdir):
    return tmpdir.join('.cache/aactivator/allowed')


@pytest.fixture
def disallowed_config(tmpdir):
    return tmpdir.join('.cache/aactivator/disallowed')


@pytest.fixture
def inactive_env(tmpdir):
    return (
        ('HOME', str(tmpdir)),
        ('AACTIVATOR_VERSION', aactivator.__version__),
    )


@pytest.fixture
def active_env(venv_path, inactive_env):
    return inactive_env + (('AACTIVATOR_ACTIVE', str(venv_path)),)


@pytest.fixture
def f_path(tmpdir):
    return tmpdir.join('f')


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


PS1 = 'TEST> '
INPUT = 'INPUT> '


def get_proc(shell, homedir):
    return pexpect.spawn(
        shell[0], list(shell[1:]),
        timeout=5,
        env={
            'COVERAGE_PROCESS_START': os.environ.get(
                'COVERAGE_PROCESS_START', '',
            ),
            'PS1': PS1,
            'TOP': os.environ.get('TOP', ''),
            'HOME': str(homedir),
            'PATH': os.path.dirname(sys.executable) + os.defpath
        },
    )


def expect_exact_better(proc, expected):
    """Uses raw strings like expect_exact, but starts looking from the start.
    """
    # I'd put a $ on the end of this regex, but sometimes the buffer comes
    # to us too quickly for our assertions
    before = proc.before
    after = proc.after
    reg = '^' + re.escape(expected)
    reg = reg.replace('\n', '\r*\n')
    try:
        proc.expect(reg)
    except pexpect.TIMEOUT:  # pragma: no cover
        message = (
            'Incorrect output.',
            '>>> Context:',
            before.decode('utf8') + after.decode('utf8'),
            '>>> Expected:',
            '    ' +
            expected.replace('\r', '').replace('\n', '\n    '),
            '>>> Actual:',
            '    ' +
            proc.buffer.replace(b'\r', b'').replace(b'\n', b'\n    ').decode('utf8'),
        )
        message = '\n'.join(message)
        if sys.version_info < (3, 0):
            message = message.encode('utf8')
        raise AssertionError(message)


def run_cmd(proc, line, output='', ps1=PS1):
    if ps1:
        expect_exact_better(proc, ps1)
    proc.sendline(line)
    expect_exact_better(proc, line + '\n' + output)


run_input = functools.partial(run_cmd, ps1='')


def parse_tests(tests):
    cmds = []
    cmd_fn = None
    cmd = None
    output = ''

    for line in tests.splitlines():
        if line.startswith((PS1, INPUT)):
            if cmd_fn is not None:
                cmds.append((cmd_fn, cmd, output))
                cmd = None
                cmd_fn = None
                output = ''
        elif INPUT in line:
            if cmd_fn is not None:
                output += line[:line.index(INPUT)]
                cmds.append((cmd_fn, cmd, output))
                cmd = None
                cmd_fn = None
                output = ''
                line = line[line.index(INPUT):]

        if line.startswith(PS1):
            cmd_fn = run_cmd
            cmd = line[len(PS1):]
        elif line.startswith(INPUT):
            cmd_fn = run_input
            cmd = line[len(INPUT):]
        else:
            output += line + '\n'

    if cmd_fn is not None:
        cmds.append((cmd_fn, cmd, output))

    return cmds


def shellquote(cmd):
    """transform a python command-list to a shell command-string"""
    from pipes import quote
    return ' '.join(quote(arg) for arg in cmd)


def run_test(shell, tests, homedir):
    proc = get_proc(shell['cmd'], homedir)
    for test_fn, test, output in parse_tests(tests):
        test_fn(proc, test, output)


@pytest.fixture(params=(
    {
        'cmd': ('/bin/bash', '--noediting', '--norc', '-is'),
        'errors': {
            'pwd_missing': 'bash: cd: {tmpdir}/d: No such file or directory',
        },
    },
    {
        # -df is basically --norc
        # -V prevents a bizarre behavior where zsh prints lots of extra whitespace
        'cmd': ('zsh', '-df', '-is', '-V', '+Z'),
        'errors': {
            'pwd_missing': 'cd: no such file or directory: {tmpdir}/d',
        },
    },
))
def shell(request):
    return request.param


def test_activates_when_cding_in(venv_path, shell, tmpdir):
    make_venv_in_tempdir(tmpdir)

    test = '''\
TEST> eval "$(aactivator init)"
TEST> echo

TEST> cd {venv_path}
aactivator will source .activate.sh and .deactivate.sh at {venv_path}.
Acceptable? (y)es (n)o (N)ever: INPUT> y
aactivator will remember this: ~/.cache/aactivator/allowed
aactivating...
TEST> echo
(aliased)
TEST> cd /
(aliased) deactivating...
TEST> echo

'''
    test = test.format(venv_path=str(venv_path))
    run_test(shell, test, tmpdir)


def test_activates_when_cding_to_child_dir(venv_path, tmpdir, shell):
    make_venv_in_tempdir(tmpdir)

    test = '''\
TEST> eval "$(aactivator init)"
TEST> echo

TEST> cd {venv_path}/child-dir
aactivator will source .activate.sh and .deactivate.sh at {venv_path}.
Acceptable? (y)es (n)o (N)ever: INPUT> y
aactivator will remember this: ~/.cache/aactivator/allowed
aactivating...
TEST> echo
(aliased)
TEST> cd /
(aliased) deactivating...
TEST> echo

'''
    test = test.format(venv_path=str(venv_path))
    run_test(shell, test, tmpdir)


def test_activates_subshell(venv_path, tmpdir, shell):
    make_venv_in_tempdir(tmpdir)

    test = '''\
TEST> eval "$(aactivator init)"
TEST> echo

TEST> cd {venv_path}
aactivator will source .activate.sh and .deactivate.sh at {venv_path}.
Acceptable? (y)es (n)o (N)ever: INPUT> y
aactivator will remember this: ~/.cache/aactivator/allowed
aactivating...
TEST> echo
(aliased)
TEST> {shell}
TEST> echo

TEST> eval "$(aactivator init)"
aactivating...
TEST> echo 2
(aliased) 2
TEST> cd /
(aliased) deactivating...
TEST> echo 3
3
TEST> exit 2>/dev/null
TEST> echo
(aliased)
TEST> cd /
(aliased) deactivating...
TEST> echo 5
5
'''
    test = test.format(
        venv_path=str(venv_path),
        shell=shellquote(shell['cmd']),
    )
    run_test(shell, test, tmpdir)


def test_complains_when_not_activated(activate, venv_path, tmpdir, shell):
    make_venv_in_tempdir(tmpdir)
    activate.chmod(0o666)

    test = '''\
TEST> eval "$(aactivator init)"
TEST> echo

TEST> cd {venv_path}
aactivator will source .activate.sh and .deactivate.sh at {venv_path}.
Acceptable? (y)es (n)o (N)ever: INPUT> y
aactivator will remember this: ~/.cache/aactivator/allowed
aactivator: Cowardly refusing to source .activate.sh because writeable by others: .activate.sh
TEST> echo

aactivator: Cowardly refusing to source .activate.sh because writeable by others: .activate.sh
TEST> cd /
TEST> echo

'''
    test = test.format(venv_path=str(venv_path))
    run_test(shell, test, tmpdir)


def test_activate_but_no_deactivate(venv_path, tmpdir, deactivate, shell):
    make_venv_in_tempdir(tmpdir)
    deactivate.remove()

    test = '''\
TEST> eval "$(aactivator init)"
TEST> echo

TEST> cd {venv_path}
aactivator will source .activate.sh and .deactivate.sh at {venv_path}.
Acceptable? (y)es (n)o (N)ever: INPUT> y
aactivator will remember this: ~/.cache/aactivator/allowed
aactivating...
TEST> echo
(aliased)
TEST> cd /
(aliased) aactivator: Cannot deactivate. File missing: {deactivate}
TEST> echo
(aliased)
'''
    test = test.format(
        venv_path=str(venv_path),
        deactivate=str(deactivate),
    )
    run_test(shell, test, tmpdir)


def test_prompting_behavior(venv_path, tmpdir, shell):
    make_venv_in_tempdir(tmpdir)

    test = '''\
TEST> eval "$(aactivator init)"
TEST> echo

TEST> cd {venv_path}
aactivator will source .activate.sh and .deactivate.sh at {venv_path}.
Acceptable? (y)es (n)o (N)ever: INPUT> herpderp
I didn't understand your response.

Acceptable? (y)es (n)o (N)ever: INPUT> n
TEST> echo

TEST> echo

TEST> echo

TEST> cd /
TEST> cd {venv_path}
aactivator will source .activate.sh and .deactivate.sh at {venv_path}.
Acceptable? (y)es (n)o (N)ever: INPUT> N
aactivator will remember this: ~/.cache/aactivator/disallowed
TEST> echo

TEST> cd /
TEST> echo

'''
    test = test.format(venv_path=str(venv_path))
    run_test(shell, test, tmpdir)


def test_pwd_goes_missing(tmpdir, shell):
    tmpdir.mkdir('d')
    make_venv_in_tempdir(tmpdir)

    test = '''\
TEST> eval "$(aactivator init)"
TEST> echo

TEST> cd {{tmpdir}}/d
TEST> rm -rf $PWD
TEST> cd $PWD
{pwd_missing}
TEST> echo

TEST> echo

'''
    test = test.format(
        pwd_missing=shell['errors']['pwd_missing'],
    ).format(
        tmpdir=str(tmpdir),
    )
    run_test(shell, test, tmpdir)


def test_version_change(venv_path, tmpdir, shell):
    """If aactivator detects a version change, it will re-init and re-activate"""
    make_venv_in_tempdir(tmpdir)

    test = '''\
TEST> eval "$(aactivator init)"
TEST> cd {venv_path}
aactivator will source .activate.sh and .deactivate.sh at {venv_path}.
Acceptable? (y)es (n)o (N)ever: INPUT> y
aactivator will remember this: ~/.cache/aactivator/allowed
aactivating...
TEST> export AACTIVATOR_VERSION=0
aactivating...
TEST> echo $AACTIVATOR_VERSION
(aliased) {version}
'''
    test = test.format(
        venv_path=str(venv_path),
        version=aactivator.__version__,
    )
    run_test(shell, test, tmpdir)


def test_cd_dash(venv_path, tmpdir, shell):
    make_venv_in_tempdir(tmpdir)
    venv2 = make_venv_in_tempdir(tmpdir, 'venv2')

    test = '''\
TEST> eval "$(aactivator init)"
TEST> cd {venv_path}/child-dir
aactivator will source .activate.sh and .deactivate.sh at {venv_path}.
Acceptable? (y)es (n)o (N)ever: INPUT> y
aactivator will remember this: ~/.cache/aactivator/allowed
aactivating...
TEST> pwd
{venv_path}/child-dir
TEST> cd {venv2}/child-dir
aactivator will source .activate.sh and .deactivate.sh at {venv2}.
Acceptable? (y)es (n)o (N)ever: INPUT> y
aactivator will remember this: ~/.cache/aactivator/allowed
(aliased) deactivating...
aactivating...
TEST> cd - > /dev/null
(aliased) deactivating...
aactivating...
TEST> pwd
{venv_path}/child-dir
TEST> cd - > /dev/null
(aliased) deactivating...
aactivating...
TEST> pwd
{venv2}/child-dir
'''
    test = test.format(
        venv_path=str(venv_path),
        venv2=str(venv2),
    )
    run_test(shell, test, tmpdir)
