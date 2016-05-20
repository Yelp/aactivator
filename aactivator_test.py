# -*- coding: utf-8 -*-
from __future__ import absolute_import
from __future__ import print_function
from __future__ import unicode_literals

import contextlib
import functools
import io
import os.path
import re
import shutil
import sys
import tempfile

import pexpect
import testify as T

import aactivator


@contextlib.contextmanager
def tempdir():
    tmpdir = tempfile.mkdtemp()
    try:
        yield tmpdir
    finally:
        shutil.rmtree(tmpdir)


def make_venv_in_tempdir(tmpdir, name='venv'):
    venv = os.path.join(tmpdir, name)
    os.makedirs(os.path.join(venv, 'child-dir'))
    with open(os.path.join(venv, 'banner'), 'w') as banner:
        banner.write('aactivating...\n')
    with open(os.path.join(venv, '.activate.sh'), 'w') as a_file:
        a_file.write('''\
cat banner
alias echo='echo "(aliased)"'
''')
    with open(os.path.join(venv, '.deactivate.sh'), 'w') as d_file:
        d_file.write('echo deactivating...\nunalias echo\n')
    return venv


class TestBase(T.TestCase):
    temp_dir = None

    @T.setup_teardown
    def make_tempdir(self):
        with tempdir() as self.temp_dir:
            yield

    @T.setup_teardown
    def cwd(self):
        olddir = os.getcwd()
        os.chdir('/')
        yield
        os.chdir(olddir)

    @T.let
    def venv_path(self):
        return os.path.join(self.temp_dir, 'venv')

    @T.let
    def activate(self):
        return os.path.join(self.venv_path, '.activate.sh')

    @T.let
    def deactivate(self):
        return os.path.join(self.venv_path, '.deactivate.sh')

    @T.let
    def allowed_config(self):
        return os.path.join(self.temp_dir, '.cache/aactivator/allowed')

    @T.let
    def disallowed_config(self):
        return os.path.join(self.temp_dir, '.cache/aactivator/disallowed')

    @T.let
    def inactive_env(self):
        return (
            ('HOME', self.temp_dir),
            ('AACTIVATOR_VERSION', aactivator.__version__),
        )

    @T.let
    def active_env(self):
        return self.inactive_env + (('AACTIVATOR_ACTIVE', self.venv_path),)


class TestAutoSourceUnits(TestBase):

    @T.class_setup_teardown
    def no_stderr(self):
        sys.stderr = open(os.devnull, 'w')
        yield
        sys.stderr = sys.__stderr__

    @T.let
    def f_path(self):
        return os.path.join(self.temp_dir, 'f')

    def test_is_safe_to_source_fine(self):
        open(self.f_path, 'a').close()
        T.assert_equal(aactivator.insecure(self.f_path), None)

    def test_is_safe_to_source_not_fine(self):
        open(self.f_path, 'a').close()
        os.chmod(self.f_path, 0o666)
        T.assert_equal(aactivator.insecure(self.f_path), self.f_path)

    def test_is_safe_to_source_also_not_fine(self):
        open(self.f_path, 'a').close()
        os.chmod(self.f_path, 0o777)
        T.assert_equal(aactivator.insecure(self.f_path), self.f_path)

    def test_directory_writeable_not_fine(self):
        open(self.f_path, 'a').close()
        os.chmod(self.temp_dir, 0o777)
        T.assert_equal(aactivator.insecure(self.f_path), self.temp_dir)

    def test_security_check_for_path_non_sourceable(self):
        open(self.f_path, 'a').close()
        os.chmod(self.f_path, 0o666)
        os.chdir(self.temp_dir)
        T.assert_equal(
            aactivator.security_check(self.f_path),
            'aactivator: Cowardly refusing to source f because writeable by others: f',
        )

    def test_security_check_for_path_sourceable(self):
        open(self.f_path, 'a').close()
        T.assert_equal(
            aactivator.security_check(self.f_path),
            None,
        )

    def test_security_check_for_path_nonexistant(self):
        T.assert_equal(
            aactivator.security_check(self.f_path),
            'aactivator: File does not exist: ' + self.f_path,
        )

    def test_get_output_nothing_special(self):
        output = aactivator.get_output(
            dict(self.inactive_env),
            self.temp_dir,
        )
        T.assert_equal(output, '')

    def test_get_output_already_sourced(self):
        make_venv_in_tempdir(self.temp_dir)
        output = aactivator.get_output(
            dict(self.active_env),
            self.venv_path,
            lambda: 'y',
        )
        T.assert_equal(output, '')

    def test_get_output_sourced_not_in_directory(self):
        make_venv_in_tempdir(self.temp_dir)
        output = aactivator.get_output(
            dict(self.active_env),
            self.temp_dir,
        )
        T.assert_equal(
            output,
            '''\
OLDPWD_bak="$OLDPWD" &&
cd {test.venv_path} &&
aactivator security-check .deactivate.sh &&
source ./.deactivate.sh
unset AACTIVATOR_ACTIVE &&
cd "$OLDPWD_bak" &&
cd {test.temp_dir} &&
unset OLDPWD_bak'''.format(test=self)
        )

    def test_get_output_sourced_deeper_in_directory(self):
        make_venv_in_tempdir(self.temp_dir)
        deeper = os.path.join(self.venv_path, 'deeper')
        os.makedirs(deeper)

        output = aactivator.get_output(
            dict(self.active_env),
            deeper,
            lambda: 'y',
        )
        T.assert_equal(output, '')

    def test_get_output_sourced_deeper_venv(self):
        make_venv_in_tempdir(self.temp_dir)
        deeper = make_venv_in_tempdir(self.venv_path, 'deeper')

        output = aactivator.get_output(
            dict(self.active_env),
            deeper,
            lambda: 'y',
        )
        T.assert_equal(
            output,
            '''\
OLDPWD_bak="$OLDPWD" &&
cd {test.venv_path} &&
aactivator security-check .deactivate.sh &&
source ./.deactivate.sh
unset AACTIVATOR_ACTIVE &&
cd "$OLDPWD_bak" &&
cd {test.venv_path}/deeper &&
unset OLDPWD_bak &&
aactivator security-check .activate.sh &&
source ./.activate.sh &&
export AACTIVATOR_ACTIVE={test.venv_path}/deeper'''.format(test=self)
        )

    def test_not_sourced_sources(self):
        make_venv_in_tempdir(self.temp_dir)
        output = aactivator.get_output(
            dict(self.inactive_env),
            self.venv_path,
            lambda: 'y',
        )
        T.assert_equal(
            output,
            '''\
aactivator security-check .activate.sh &&
source ./.activate.sh &&
export AACTIVATOR_ACTIVE=''' + self.venv_path
        )

    def test_get_output_change_venv(self):
        make_venv_in_tempdir(self.temp_dir)
        venv2 = make_venv_in_tempdir(self.temp_dir, 'venv2')
        output = aactivator.get_output(
            dict(self.active_env),
            venv2,
            lambda: 'y',
        )
        T.assert_equal(
            output,
            '''\
OLDPWD_bak="$OLDPWD" &&
cd {test.venv_path} &&
aactivator security-check .deactivate.sh &&
source ./.deactivate.sh
unset AACTIVATOR_ACTIVE &&
cd "$OLDPWD_bak" &&
cd {test.venv_path}2 &&
unset OLDPWD_bak &&
aactivator security-check .activate.sh &&
source ./.activate.sh &&
export AACTIVATOR_ACTIVE={test.venv_path}2'''.format(test=self)
        )

    def test_get_output_pwd_goes_missing(self):
        make_venv_in_tempdir(self.temp_dir)
        os.chdir(self.venv_path)
        shutil.rmtree(self.venv_path)
        output = aactivator.get_output(
            dict(self.inactive_env),
            self.venv_path,
            lambda: 'n',
        )
        T.assert_equal(output, '')

    def config(self, answer):
        return aactivator.ActivateConfig(
            dict(self.inactive_env),
            lambda: print(answer, file=sys.stderr) or answer,
        )

    @property
    def yes_config(self):
        return self.config('y')

    @property
    def no_config(self):
        return self.config('n')

    @property
    def never_config(self):
        return self.config('N')

    @property
    def eof_config(self):
        def raise_eoferror():
            raise EOFError()
        return aactivator.ActivateConfig(
            dict(self.inactive_env), raise_eoferror,
        )

    def test_prompt_loop_answer_yes(self):
        make_venv_in_tempdir(self.temp_dir)
        T.assert_equal(
            self.yes_config.find_allowed(self.venv_path), self.venv_path,
        )
        T.assert_is(os.path.exists(self.allowed_config), True)
        T.assert_equal(
            io.open(self.allowed_config).read(), self.venv_path + '\n',
        )

    def test_no_config_not_allowed(self):
        make_venv_in_tempdir(self.temp_dir)
        T.assert_is(self.no_config.find_allowed(self.venv_path), None)
        # Saying no should not permanently save anything
        T.assert_is(os.path.exists(self.allowed_config), False)
        T.assert_is(os.path.exists(self.disallowed_config), False)

    def test_eof_treated_like_no(self):
        make_venv_in_tempdir(self.temp_dir)
        T.assert_is(self.eof_config.find_allowed(self.venv_path), None)
        # Saying no should not permanently save anything
        T.assert_is(os.path.exists(self.allowed_config), False)
        T.assert_is(os.path.exists(self.disallowed_config), False)

    def test_never_config_not_allowed(self):
        make_venv_in_tempdir(self.temp_dir)
        T.assert_is(self.never_config.find_allowed(self.venv_path), None)
        T.assert_is(os.path.exists(self.disallowed_config), True)
        T.assert_equal(
            io.open(self.disallowed_config).read(), self.venv_path + '\n'
        )

    def test_yes_config_is_remembered(self):
        make_venv_in_tempdir(self.temp_dir)
        T.assert_equal(
            self.yes_config.find_allowed(self.venv_path), self.venv_path,
        )
        T.assert_equal(
            self.no_config.find_allowed(self.venv_path), self.venv_path,
        )

    def test_never_is_remembered(self):
        make_venv_in_tempdir(self.temp_dir)
        T.assert_is(self.never_config.find_allowed(self.venv_path), None)
        T.assert_is(self.yes_config.find_allowed(self.venv_path), None)

    def test_not_owned_by_me_is_not_activatable(self):
        make_venv_in_tempdir(self.temp_dir)
        T.assert_is(
            self.yes_config.is_allowed(self.activate, _getuid=lambda: -1),
            False,
        )

    def test_no_is_remembered_until_cd_out(self):
        venv = make_venv_in_tempdir(self.temp_dir)
        T.assert_is(self.no_config.find_allowed(self.venv_path), None)
        T.assert_is(self.yes_config.find_allowed(self.venv_path), None)

        # cd to a child directory shouldn't forget the answer
        child_dir = os.path.join(venv, 'child-dir')
        T.assert_is(self.yes_config.find_allowed(child_dir), None)

        # cd to a parent directory directory (and back) should
        T.assert_is(self.yes_config.find_allowed('/'), None)
        T.assert_equal(self.yes_config.find_allowed(child_dir), self.venv_path)


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
            'HOME': homedir,
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
    proc = get_proc(shell, homedir)
    for test_fn, test, output in parse_tests(tests):
        test_fn(proc, test, output)


class IntegrationTestBase(TestBase):
    __test__ = False
    SHELL = None

    def test_activates_when_cding_in(self):
        make_venv_in_tempdir(self.temp_dir)

        test = '''\
TEST> eval "$(aactivator init)"
TEST> echo

TEST> cd {test.venv_path}
aactivator will source .activate.sh and .deactivate.sh at {test.venv_path}.
Acceptable? (y)es (n)o (N)ever: INPUT> y
aactivator will remember this: ~/.cache/aactivator/allowed
aactivating...
TEST> echo
(aliased)
TEST> cd /
(aliased) deactivating...
TEST> echo

'''
        test = test.format(test=self)
        run_test(self.SHELL, test, self.temp_dir)

    def test_activates_when_cding_to_child_dir(self):
        make_venv_in_tempdir(self.temp_dir)

        test = '''\
TEST> eval "$(aactivator init)"
TEST> echo

TEST> cd {test.venv_path}/child-dir
aactivator will source .activate.sh and .deactivate.sh at {test.venv_path}.
Acceptable? (y)es (n)o (N)ever: INPUT> y
aactivator will remember this: ~/.cache/aactivator/allowed
aactivating...
TEST> echo
(aliased)
TEST> cd /
(aliased) deactivating...
TEST> echo

'''
        test = test.format(test=self)
        run_test(self.SHELL, test, self.temp_dir)

    def test_activates_subshell(self):
        make_venv_in_tempdir(self.temp_dir)

        test = '''\
TEST> eval "$(aactivator init)"
TEST> echo

TEST> cd {test.venv_path}
aactivator will source .activate.sh and .deactivate.sh at {test.venv_path}.
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
        test = test.format(test=self, shell=shellquote(self.SHELL))
        run_test(self.SHELL, test, self.temp_dir)

    def test_complains_when_not_activated(self):
        make_venv_in_tempdir(self.temp_dir)
        os.chmod(self.activate, 0o666)

        test = '''\
TEST> eval "$(aactivator init)"
TEST> echo

TEST> cd {test.venv_path}
aactivator will source .activate.sh and .deactivate.sh at {test.venv_path}.
Acceptable? (y)es (n)o (N)ever: INPUT> y
aactivator will remember this: ~/.cache/aactivator/allowed
aactivator: Cowardly refusing to source .activate.sh because writeable by others: .activate.sh
TEST> echo

aactivator: Cowardly refusing to source .activate.sh because writeable by others: .activate.sh
TEST> cd /
TEST> echo

'''
        test = test.format(test=self)
        run_test(self.SHELL, test, self.temp_dir)

    def test_activate_but_no_deactivate(self):
        make_venv_in_tempdir(self.temp_dir)
        os.remove(self.deactivate)

        test = '''\
TEST> eval "$(aactivator init)"
TEST> echo

TEST> cd {test.venv_path}
aactivator will source .activate.sh and .deactivate.sh at {test.venv_path}.
Acceptable? (y)es (n)o (N)ever: INPUT> y
aactivator will remember this: ~/.cache/aactivator/allowed
aactivating...
TEST> echo
(aliased)
TEST> cd /
(aliased) aactivator: Cannot deactivate. File missing: {test.deactivate}
TEST> echo
(aliased)
'''
        test = test.format(test=self)
        run_test(self.SHELL, test, self.temp_dir)

    def test_prompting_behaviour(self):
        make_venv_in_tempdir(self.temp_dir)

        test = '''\
TEST> eval "$(aactivator init)"
TEST> echo

TEST> cd {test.venv_path}
aactivator will source .activate.sh and .deactivate.sh at {test.venv_path}.
Acceptable? (y)es (n)o (N)ever: INPUT> herpderp
I didn't understand your response.

Acceptable? (y)es (n)o (N)ever: INPUT> n
TEST> echo

TEST> echo

TEST> echo

TEST> cd /
TEST> cd {test.venv_path}
aactivator will source .activate.sh and .deactivate.sh at {test.venv_path}.
Acceptable? (y)es (n)o (N)ever: INPUT> N
aactivator will remember this: ~/.cache/aactivator/disallowed
TEST> echo

TEST> cd /
TEST> echo

'''
        test = test.format(test=self)
        run_test(self.SHELL, test, self.temp_dir)

    def test_pwd_goes_missing(self):
        os.mkdir(os.path.join(self.temp_dir, 'd'))
        make_venv_in_tempdir(self.temp_dir)

        test = '''\
TEST> eval "$(aactivator init)"
TEST> echo

TEST> cd {test.temp_dir}/d
TEST> rm -rf $PWD
TEST> cd $PWD
{test.errors.pwd_missing}
TEST> echo

TEST> echo

'''
        test = test.format(test=self)
        run_test(self.SHELL, test, self.temp_dir)

    def test_version_change(self):
        """If aactivator detects a version change, it will re-init and re-activate"""
        make_venv_in_tempdir(self.temp_dir)

        test = '''\
TEST> eval "$(aactivator init)"
TEST> cd {test.venv_path}
aactivator will source .activate.sh and .deactivate.sh at {test.venv_path}.
Acceptable? (y)es (n)o (N)ever: INPUT> y
aactivator will remember this: ~/.cache/aactivator/allowed
aactivating...
TEST> export AACTIVATOR_VERSION=0
aactivating...
TEST> echo $AACTIVATOR_VERSION
(aliased) {version}
'''
        test = test.format(test=self, version=aactivator.__version__)
        run_test(self.SHELL, test, self.temp_dir)

    def test_cd_dash(self):
        make_venv_in_tempdir(self.temp_dir)
        venv2 = make_venv_in_tempdir(self.temp_dir, 'venv2')

        test = '''\
TEST> eval "$(aactivator init)"
TEST> cd {test.venv_path}/child-dir
aactivator will source .activate.sh and .deactivate.sh at {test.venv_path}.
Acceptable? (y)es (n)o (N)ever: INPUT> y
aactivator will remember this: ~/.cache/aactivator/allowed
aactivating...
TEST> pwd
{test.venv_path}/child-dir
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
{test.venv_path}/child-dir
TEST> cd - > /dev/null
(aliased) deactivating...
aactivating...
TEST> pwd
{venv2}/child-dir
'''
        test = test.format(test=self, venv2=venv2)
        run_test(self.SHELL, test, self.temp_dir)


class BashIntegrationTest(IntegrationTestBase):
    SHELL = ('/bin/bash', '--noediting', '--norc', '-is')

    @property
    def errors(self):
        class errors(object):
            pwd_missing = 'bash: cd: {test.temp_dir}/d: No such file or directory'.format(test=self)
        return errors


class ZshIntegrationTest(IntegrationTestBase):
    # -df is basically --norc
    # -V prevents a bizarre behavior where zsh prints lots of extra whitespace
    SHELL = ('zsh', '-df', '-is', '-V', '+Z')

    @property
    def errors(self):
        class errors(object):
            pwd_missing = 'cd: no such file or directory: {test.temp_dir}/d'.format(test=self)
        return errors
