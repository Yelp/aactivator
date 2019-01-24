# -*- coding: utf-8 -*-
from __future__ import absolute_import
from __future__ import print_function
from __future__ import unicode_literals

import functools
import os.path
import re
import shutil
import sys

import pexpect
import pytest

import aactivator
from testing import make_venv_in_tempdir


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


def test_complains_parent_directory_insecure(venv_path, tmpdir, shell):
    make_venv_in_tempdir(tmpdir)
    venv_path.chmod(0o777)

    test = '''\
TEST> eval "$(aactivator init)"
TEST> echo

TEST> cd {venv_path}
aactivator will source .activate.sh and .deactivate.sh at {venv_path}.
Acceptable? (y)es (n)o (N)ever: INPUT> y
aactivator will remember this: ~/.cache/aactivator/allowed
aactivator: Cowardly refusing to source .activate.sh because writeable by others: .
TEST> echo

aactivator: Cowardly refusing to source .activate.sh because writeable by others: .
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


def test_aactivator_goes_missing_no_output(venv_path, shell, tmpdir):
    make_venv_in_tempdir(tmpdir)

    exe = tmpdir.join('exe').strpath
    src = os.path.join(os.path.dirname(sys.executable), 'aactivator')
    shutil.copy(src, exe)

    test = '''\
TEST> eval "$({exe} init)"
TEST> rm {exe}
TEST> echo

TEST> cd {venv_path}
TEST> echo

'''
    test = test.format(venv_path=str(venv_path), exe=exe)
    run_test(shell, test, tmpdir)
