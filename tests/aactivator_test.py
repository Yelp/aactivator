# -*- coding: utf-8 -*-
from __future__ import absolute_import
from __future__ import unicode_literals
from __future__ import print_function

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

from . import aactivator


DEBUG = os.environ.get('DEBUG')


@contextlib.contextmanager
def tempdir():
    tmpdir = tempfile.mkdtemp()
    try:
        yield tmpdir
    finally:
        if DEBUG:
            print('not deleting: %s' % tmpdir)
        else:
            shutil.rmtree(tmpdir)


def make_venv_in_tempdir(tmpdir, name='venv'):
    venv = os.path.join(tmpdir, name)
    os.makedirs(os.path.join(venv, 'child-dir'))
    with open(os.path.join(venv, 'banner'), 'w') as banner:
        banner.write('aactivating...\n')
    with open(os.path.join(venv, '.activate.sh'), 'w') as a_file:
        a_file.write('''\
cat banner
export MY_ENV_VAR='($MY_ENV_VAR set)'
alias echo='echo "(aliased)"'
''')
    with open(os.path.join(venv, '.deactivate.sh'), 'w') as d_file:
        d_file.write('echo deactivating...\n')

    state = aactivator.state_path({'HOME': tmpdir, 'AACTIVATOR_PID': '$PID'}, venv)
    aactivator.mkdirp(state)
    with open(os.path.join(state, 'environ'), 'w') as environ:
        environ.write('A=C\0D=C\0AACTIVATOR_PID=$PID\0HOME=' + tmpdir)
    return venv


aactivator_path = os.path.realpath(aactivator.__file__.rstrip('c'))


class TestBase(T.TestCase):
    temp_dir = None

    @T.setup_teardown
    def make_tempdir(self):
        with tempdir() as self.temp_dir:
            os.symlink(aactivator_path, self.AACTIVATOR)
            yield

    @T.setup_teardown
    def cwd(self):
        olddir = os.getcwd()
        os.chdir('/')
        yield
        os.chdir(olddir)

    @T.let
    def AACTIVATOR(self):
        return os.path.join(self.temp_dir, 'aactivator')

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


class TestAutoSourceUnits(TestBase):
    @T.class_setup_teardown
    def no_stderr(self):
        if not DEBUG:
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
            {
            },
            self.temp_dir,
        )
        T.assert_equal(output, '')

    def test_get_output_already_sourced(self):
        make_venv_in_tempdir(self.temp_dir)
        output = aactivator.get_output(
            {
                'AACTIVATOR_ACTIVE': self.venv_path,
                'HOME': self.temp_dir,
            },
            self.venv_path,
            lambda: 'y',
        )
        T.assert_equal(output, '')

    def test_not_sourced_sources(self):
        make_venv_in_tempdir(self.temp_dir)
        output = aactivator.get_output(
            {
                'HOME': self.temp_dir,
                'AACTIVATOR_PID': '$PID',
            },
            self.venv_path,
            lambda: 'y',
        )
        T.assert_equal(
            output,
            r'''_aa_state='{tmp}/.run/aactivator{venv}/$PID' &&
alias | sed 's/^\(alias \)\?/alias /' > "$_aa_state/alias" &&
sh -c 'exec cat /proc/$$/environ' > "$_aa_state/environ" &&
export AACTIVATOR_ACTIVE={venv} &&
-aa-source {venv}/.activate.sh &&
[ $_aa_ok ] || eval "$(aactivator deaactivate)"'''
            .format(tmp=self.temp_dir, venv=self.venv_path)
        )

    def test_get_output_sourced_not_in_directory(self):
        make_venv_in_tempdir(self.temp_dir)
        output = aactivator.get_output(
            {
                'AACTIVATOR_ACTIVE': self.venv_path,
                'HOME': self.temp_dir,
                'AACTIVATOR_PID': '$PID',
            },
            self.temp_dir,
        )
        T.assert_equal(
            output,
            r'''export A=C
unset AACTIVATOR_ACTIVE
export D=C
_aa_state='{tmp}/.run/aactivator{venv}/$PID'
unalias -a
-aa-source "$_aa_state/alias" &&
rm -r $_aa_state'''
            .format(venv=self.venv_path, tmp=self.temp_dir),
        )

    def test_get_output_sourced_deeper_in_directory(self):
        make_venv_in_tempdir(self.temp_dir)
        deeper = os.path.join(self.venv_path, 'deeper')
        os.makedirs(deeper)

        output = aactivator.get_output(
            {
                'AACTIVATOR_ACTIVE': self.venv_path,
                'HOME': self.temp_dir,
            },
            deeper,
            lambda: 'y',
        )
        T.assert_equal(output, '')

    def test_get_output_sourced_deeper_venv(self):
        make_venv_in_tempdir(self.temp_dir)
        deeper = make_venv_in_tempdir(self.venv_path, 'deeper')

        output = aactivator.get_output(
            {
                'AACTIVATOR_ACTIVE': self.venv_path,
                'HOME': self.temp_dir,
                'AACTIVATOR_PID': '$PID',
            },
            deeper,
            lambda: 'y',
        )
        T.assert_equal(
            output,
            r'''export A=C
unset AACTIVATOR_ACTIVE
export D=C
_aa_state='{tmp}/.run/aactivator{venv}/$PID'
unalias -a
-aa-source "$_aa_state/alias" &&
rm -r $_aa_state &&
_aa_state='{tmp}/.run/aactivator{venv}/deeper/$PID' &&
alias | sed 's/^\(alias \)\?/alias /' > "$_aa_state/alias" &&
sh -c 'exec cat /proc/$$/environ' > "$_aa_state/environ" &&
export AACTIVATOR_ACTIVE={venv}/deeper &&
-aa-source {venv}/deeper/.activate.sh &&
[ $_aa_ok ] || eval "$(aactivator deaactivate)"'''
            .format(tmp=self.temp_dir, venv=self.venv_path)
        )

    def test_get_output_change_venv(self):
        make_venv_in_tempdir(self.temp_dir)
        venv2 = make_venv_in_tempdir(self.temp_dir, 'venv2')
        output = aactivator.get_output(
            {
                'AACTIVATOR_ACTIVE': self.venv_path,
                'HOME': self.temp_dir,
                'A': '1',
                'AACTIVATOR_PID': '$PID',
            },
            venv2,
            lambda: 'y',
        )
        T.assert_equal(
            output,
            r'''export A=C
unset AACTIVATOR_ACTIVE
export D=C
_aa_state='{home}/.run/aactivator{0}/$PID'
unalias -a
-aa-source "$_aa_state/alias" &&
rm -r $_aa_state &&
_aa_state='{home}/.run/aactivator{1}/$PID' &&
alias | sed 's/^\(alias \)\?/alias /' > "$_aa_state/alias" &&
sh -c 'exec cat /proc/$$/environ' > "$_aa_state/environ" &&
export AACTIVATOR_ACTIVE={1} &&
-aa-source {1}/.activate.sh &&
[ $_aa_ok ] || eval "$(aactivator deaactivate)"'''
            .format(
                self.venv_path,
                venv2,
                home=self.temp_dir,
            ),
        )

    def test_get_output_pwd_goes_missing(self):
        make_venv_in_tempdir(self.temp_dir)
        os.chdir(self.venv_path)
        shutil.rmtree(self.venv_path)
        output = aactivator.get_output(
            {
                'HOME': self.temp_dir,
            },
            self.venv_path,
            lambda: 'n',
        )
        T.assert_equal(output, '')

    def config(self, home, answer):
        return aactivator.ActivateConfig(
            {'HOME': home},
            lambda: print(answer, file=sys.stderr) or answer,
        )

    @property
    def yes_config(self):
        return self.config(self.temp_dir, 'y')

    @property
    def no_config(self):
        return self.config(self.temp_dir, 'n')

    @property
    def never_config(self):
        return self.config(self.temp_dir, 'N')

    @property
    def eof_config(self):
        def raise_EOFError():
            raise EOFError()
        return aactivator.ActivateConfig(
            {'HOME': self.temp_dir}, raise_EOFError,
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
    reg = reg.replace('\\$\\$PID', '[0-9]+')
    try:
        proc.expect(reg)
    except pexpect.TIMEOUT:
        message = (
            'Incorrect output.',
            '>>> Context:',
            before + after,
            '>>> Expected:',
            '    ' +
            expected.replace('\r', '').replace('\n', '↵\n    '),
            '>>> Actual:',
            '    ' +
            proc.buffer.replace('\r', '').replace('\n', '↵\n    '),
        )
        message = '\n'.join(message)
        message = message.encode('UTF-8')
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
TEST> eval "$(python {test.AACTIVATOR} init)"
TEST> echo

TEST> cd {test.venv_path}
aactivator will source .activate.sh at {test.venv_path}.
Acceptable? (y)es (n)o (N)ever: INPUT> y
aactivator will remember this: ~/.cache/aactivator/allowed
aactivating...
TEST> echo
(aliased)
TEST> cd /
TEST> echo

'''
        test = test.format(test=self)
        run_test(self.SHELL, test, self.temp_dir)

    def test_activates_when_cding_to_child_dir(self):
        make_venv_in_tempdir(self.temp_dir)

        test = '''\
TEST> eval "$(python {test.AACTIVATOR} init)"
TEST> echo

TEST> cd {test.venv_path}/child-dir
aactivator will source .activate.sh at {test.venv_path}.
Acceptable? (y)es (n)o (N)ever: INPUT> y
aactivator will remember this: ~/.cache/aactivator/allowed
aactivating...
TEST> echo
(aliased)
TEST> pwd
{test.venv_path}/child-dir
TEST> cd /
TEST> echo

'''
        test = test.format(test=self)
        run_test(self.SHELL, test, self.temp_dir)

    def test_activates_subshell(self):
        make_venv_in_tempdir(self.temp_dir)

        test = '''\
TEST> eval "$(python {test.AACTIVATOR} init)"
TEST> echo

TEST> cd {test.venv_path}
aactivator will source .activate.sh at {test.venv_path}.
Acceptable? (y)es (n)o (N)ever: INPUT> y
aactivator will remember this: ~/.cache/aactivator/allowed
aactivating...
TEST> echo
(aliased)
TEST> {shell}
TEST> echo

TEST> eval "$(python {test.AACTIVATOR} init)"
aactivating...
TEST> echo 2
(aliased) 2
TEST> cd /
TEST> echo 3
3
TEST> exit 2>/dev/null
TEST> echo
(aliased)
TEST> cd /
TEST> echo 5
5
'''
        test = test.format(test=self, shell=shellquote(self.SHELL))
        run_test(self.SHELL, test, self.temp_dir)

    def test_complains_when_not_activated(self):
        make_venv_in_tempdir(self.temp_dir)
        os.chmod(self.activate, 0o666)

        test = '''\
TEST> eval "$(python {test.AACTIVATOR} init)"
TEST> echo

TEST> cd {test.venv_path}
aactivator will source .activate.sh at {test.venv_path}.
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
TEST> eval "$(python {test.AACTIVATOR} init)"
TEST> echo

TEST> cd {test.venv_path}
aactivator will source .activate.sh at {test.venv_path}.
Acceptable? (y)es (n)o (N)ever: INPUT> y
aactivator will remember this: ~/.cache/aactivator/allowed
aactivating...
TEST> env | grep ITWORKS
ITWORKS=1
TEST> echo 1 $ITWORKS
(aliased) 1 1
TEST> cd /
TEST> echo 2 $ITWORKS
2
'''
        test = test.format(test=self)
        run_test(self.SHELL, test, self.temp_dir)

    def test_activate_fails(self):
        make_venv_in_tempdir(self.temp_dir)

        test = '''\
TEST> tail -n 999 {test.venv_path}/.activate.sh {test.venv_path}/banner {test.venv_path}/.deactivate.sh
==> {test.venv_path}/.activate.sh <==
cat banner
export MY_ENV_VAR='($MY_ENV_VAR set)'
alias echo='echo "(aliased)"'

==> {test.venv_path}/banner <==
aactivating...

==> {test.venv_path}/.deactivate.sh <==
echo deactivating...
TEST> echo 'source activate2; echo ok' >> {test.venv_path}/.activate.sh
TEST> eval "$(python {test.AACTIVATOR} init)"
TEST> echo

TEST> cd {test.venv_path}
aactivator will source .activate.sh at {test.venv_path}.
Acceptable? (y)es (n)o (N)ever: INPUT> y
aactivator will remember this: ~/.cache/aactivator/allowed
aactivating...
{test.errors.no_such_file_activate2}
aactivator: command failed: aactivate {test.venv_path}/.activate.sh
TEST> echo 1 "$MY_ENV_VAR"
1 
aactivating...
{test.errors.no_such_file_activate2}
aactivator: command failed: aactivate {test.venv_path}/.activate.sh
TEST> echo 'do-activate3() {{ source ./activate3; }}; do-activate3' > activate2
aactivating...
{test.errors.no_such_file_activate3}
(aliased) ok
aactivator: command failed: aactivate {test.venv_path}/.activate.sh
TEST> echo echo from activate2: > activate2
aactivating...
(aliased) from activate2:
(aliased) ok
TEST> echo 2 "$MY_ENV_VAR"
(aliased) 2 ($MY_ENV_VAR set)
TEST> cd /
(aliased) deactivating...
TEST> echo 3 "$MY_ENV_VAR"
3 
'''
        test = test.format(test=self)
        run_test(self.SHELL, test, self.temp_dir)


    def test_aa_load_fails(self):
        make_venv_in_tempdir(self.temp_dir)

        test = '''\
TEST> eval "$(python {test.AACTIVATOR} init)"
TEST> cd {test.venv_path}
aactivator will source .activate.sh at {test.venv_path}.
Acceptable? (y)es (n)o (N)ever: INPUT> y
aactivator will remember this: ~/.cache/aactivator/allowed
aactivating...
TEST> echo 1 "$MY_ENV_VAR"
(aliased) 1 ($MY_ENV_VAR set)
TEST> rm -rf ~/.run/aactivator
TEST> cd /
Could not deaactivate, due to: [Errno 2] No such file or directory: '{test.temp_dir}/.run/aactivator{test.venv_path}/$$PID/environ'
TEST> echo 2 "$MY_ENV_VAR"
(aliased) 2 ($MY_ENV_VAR set)
'''
        test = test.format(test=self)
        run_test(self.SHELL, test, self.temp_dir)


    def test_prompting_behaviour(self):
        make_venv_in_tempdir(self.temp_dir)

        test = '''\
TEST> eval "$(python {test.AACTIVATOR} init)"
TEST> echo

TEST> cd {test.venv_path}
aactivator will source .activate.sh at {test.venv_path}.
Acceptable? (y)es (n)o (N)ever: INPUT> herpderp
I didn't understand your response.

Acceptable? (y)es (n)o (N)ever: INPUT> n
TEST> echo

TEST> echo

TEST> echo

TEST> cd /
TEST> cd {test.venv_path}
aactivator will source .activate.sh at {test.venv_path}.
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
TEST> eval "$(python {test.AACTIVATOR} init)"
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


class Bash(object):
    SHELL = ('/bin/bash', '--noediting', '--norc', '-is')

class BashIntegrationTest(Bash, IntegrationTestBase):
    @property
    def errors(self):
        class errors(object):
            no_deactivate = 'bash: {test.venv_path}/.deactivate.sh: No such file or directory'.format(test=self)
            no_such_file_activate2 = 'bash: activate2: No such file or directory'
            no_such_file_activate3 = 'bash: ./activate3: No such file or directory'
            pwd_missing = 'bash: cd: {test.temp_dir}/d: No such file or directory'.format(test=self)
        return errors


class Zsh(object):
    # -df is basically --norc
    # -V prevents a bizarre behavior where zsh prints lots of extra whitespace
    # use find_executable to resolve the $PATH, so I can use my own zsh compilation.
    from distutils.spawn import find_executable
    SHELL = (find_executable('zsh'), '-df', '-is', '-V', '+Z')


class ZshIntegrationTest(Zsh, IntegrationTestBase):
    @property
    def errors(self):
        class errors(object):
            no_deactivate = 'aactivator-source:.:2: no such file or directory: {test.venv_path}/.deactivate.sh'.format(test=self)
            no_such_file_activate2 = './.activate.sh:source:1: no such file or directory: activate2'
            no_such_file_activate3 = 'f:source: no such file or directory: ./activate3'
            pwd_missing = 'cd: no such file or directory: {test.temp_dir}/d'.format(test=self)
        return errors


class ErrorHandlerTestBase(TestBase):
    __test__ = False
    SHELL = None

    def test_can_succeed(self):
        test = '''\
TEST> eval "$(python {test.AACTIVATOR} init)"
TEST> echo "false || echo all clear" | -aa-source /dev/stdin
all clear
TEST> echo ok
ok
'''
        test = test.format(test=self)
        run_test(self.SHELL, test, self.temp_dir)

    def test_can_handle_false(self):
        test = '''\
TEST> eval "$(python {test.AACTIVATOR} init)"
TEST> echo "echo 1; false; echo 2" | -aa-source /dev/stdin
1
aactivator: failed to source /dev/stdin
'''
        test = test.format(test=self)
        run_test(self.SHELL, test, self.temp_dir)

    def test_can_handle_source(self):
        test = '''\
TEST> eval "$(python {test.AACTIVATOR} init)"
TEST> echo ". ./wat" | -aa-source /dev/stdin
{test.errors.no_such_file_wat}
aactivator: failed to source /dev/stdin
'''
        test = test.format(test=self)
        run_test(self.SHELL, test, self.temp_dir)

    def test_can_handle_function(self):
        test = '''\
TEST> eval "$(python {test.AACTIVATOR} init)"
TEST> fail() {{ echo failing...; false; echo womp; }}
TEST> echo fail | -aa-source /dev/stdin
failing...
aactivator: failed to source /dev/stdin
'''
        test = test.format(test=self)
        run_test(self.SHELL, test, self.temp_dir)

    def test_can_handle_nested_functions(self):
        test = '''\
TEST> eval "$(python {test.AACTIVATOR} init)"
TEST> run() {{ echo "$@"; "$@"; echo DONE; }}
TEST> fail() {{ echo failing...; false; echo womp; }}
TEST> echo "run run fail" | -aa-source /dev/stdin
run fail
fail
failing...
DONE
DONE
aactivator: failed to source /dev/stdin
'''
        test = test.format(test=self)
        run_test(self.SHELL, test, self.temp_dir)


class BashErrorHandlerTest(Bash, ErrorHandlerTestBase):
    class errors(object):
        no_such_file_wat = 'bash: ./wat: No such file or directory'


class ZshErrorHandlerTest(Zsh, ErrorHandlerTestBase):
    class errors(object):
        no_such_file_wat = '(eval):.:1: no such file or directory: ./wat'
