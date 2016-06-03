#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""
FIXME: the below doc is ahead of the code
Usage: eval "$(aactivator init)"

aactivator is a script for automatically sourcing environments in an interactive shell.
The interface for using this is one files:

    aactivate.sh: when sourced, this file activates your environment

A typical setup in a python project:

    $ cat .activate.sh
    . ./venv/bin/activate

If an environment is already active it will not be re-activated.
If a different project is activated, the previous project will be deactivated beforehand.

aactivator will ask before automatically sourcing environments, and optionally
remember your answer. You can later adjust your per-project preferences in the
~/.config/aactivator/ directory.

see also: https://trac.yelpcorp.com/wiki/aactivator
"""
from __future__ import absolute_import
from __future__ import print_function
from __future__ import unicode_literals

import io
import os.path
from os.path import relpath
import sys
from pipes import quote

# This script should not depend on anything but py26-stdlib


ENVIRONMENT_VARIABLE = 'AACTIVATOR_ACTIVE'
ACTIVATE = '.activate.sh'
__version__ = '0.2'


def init(arg0):
    arg0 = os.path.realpath(arg0)
    cmd = 'eval -- "`aactivator`"'
    return r'''
export AACTIVATOR_VERSION={version}
export AACTIVATOR_PID=$$
-aa-eval() {{ "$@"; }}
# Don't worry! I unit-tested it:
-aa-source() {{
    {arg0} security-check "$1" || return 1
    # a flag to let us know if anything failed
    _aa_ok=1 &&
    # unset the flag if anything fails
    \trap 'unset _aa_ok; return 0' ERR &&
    # persist our ERR trap through function calls too
    set -E &&
    # an && here would disable the ERR trap
    -aa-eval source "$1"
    set +E &&
    \trap - ERR &&
    if ! [ "$_aa_ok" ]; then
        \echo 'aactivator: failed to source '"$1" >&2
        return 1
    fi
}}
alias aactivator={arg0}
unset {varname}
if [ -n "$ZSH_VERSION" ]; then
    precmd_aactivator() {{
        {cmd}
    }}
    precmd_functions=(precmd_aactivator $precmd_functions)
else
    if ! ( \echo "$PROMPT_COMMAND" | \grep -Fq '{cmd}' ); then
        PROMPT_COMMAND='{cmd}; '"$PROMPT_COMMAND"
    fi
fi'''.format(version=__version__, arg0=arg0, cmd=cmd, varname=ENVIRONMENT_VARIABLE)


def env_parse_file(path):
    """parse the format seen in /proc/$$/environ"""
    with open(path) as path:
        return dict([
            env.split('=', 1)
            for env in path.read().split('\0')
            if env
        ])


def env_diff(old, new):
    result = {}
    new = dict(new)
    for key, oldval in sorted(old.items()):
        newval = new.pop(key, None)
        if oldval == newval:
            continue
        else:
            result[key] = newval
    result.update(new)
    return result


def env_shell_commands(env):
    """What are the shell commands necessary to set the environment like so?"""
    # We'll see the error and continue on if any of these fail.
    # I think that's proper.
    return tuple([
        'unset %s' % quote(key)
        if val is None else
        'export %s=%s' % (quote(key), quote(val))
        for key, val in sorted(env.items())
    ])


def get_filesystem_id(path):
    try:
        return os.stat(path).st_dev
    except OSError as error:
        if error.errno == 2:  # no such file
            return None
        else:
            raise


def insecure_inode(path):
    """This particular inode can be altered by someone other than the owner"""
    import stat
    pathstat = os.stat(path).st_mode
    # Directories with a sticky bit are alwas acceptable.
    if os.path.isdir(path) and pathstat & stat.S_ISVTX:
        return False
    # The path is writable by someone who is not us.
    elif pathstat & (stat.S_IWGRP | stat.S_IWOTH):
        return True
    else:
        return False


def first(iterable, predicate):
    for x in iterable:
        if predicate(x):
            return x


def insecure(path):
    """Find an insecure path, at or above this one"""
    return first(search_parent_paths(path), insecure_inode)


def search_parent_paths(path):
    original_fs_id = fs_id = get_filesystem_id(path)
    previous_path = None
    while original_fs_id == fs_id and path != previous_path:
        yield path
        previous_path = path
        path = os.path.dirname(path)
        fs_id = get_filesystem_id(path)


def mkdirp(path, mode=0755):
    try:
        os.makedirs(path, mode)
    except OSError:
        if os.path.isdir(path):
            return
        else:
            raise


def _get_lines_if_there(path):
    if os.path.exists(path):
        return io.open(path).read().splitlines()
    else:
        return []


class ConfigFile(object):
    def __init__(self, directory, name):
        self.path = os.path.join(directory, name)
        self.lines = frozenset(_get_lines_if_there(self.path))

    def write(self, mode, value):
        mkdirp(os.path.dirname(self.path))
        with io.open(self.path, mode) as file_obj:
            file_obj.write(value)

    def append(self, value):
        self.write('a', value + '\n')


def path_is_under(path, under):
    relpath = os.path.relpath(path, under).split('/')
    return not relpath[:1] == ['..']


def user_dir(env, var, default):
    # stolen from pip.utils.appdirs.user_cache_dir
    # expanduser doesn't take an env argument -.-
    orig, os.environ = os.environ, env
    try:
        return os.path.expanduser(env.get(var, default))
    finally:
        os.environ = orig


def user_config_dir(env):
    # TODO: return user_dir(env, 'XDG_CONFIG_HOME', '~/.config')
    return user_dir(env, 'XDG_CACHE_HOME', '~/.cache')


def user_run_dir(env):
    return user_dir(env, 'XDG_RUNTIME_DIR', '~/.run')


def state_path(env, dname):
    pid = env['AACTIVATOR_PID']
    return os.path.join(user_run_dir(env), 'aactivator', dname.lstrip('/'), pid)


class ActivateConfig(object):
    def __init__(self, env, get_input):
        self.env = env
        self.get_input = get_input
        self.path = os.path.join(user_config_dir(self.env), 'aactivator')
        self.allowed = ConfigFile(self.path, 'allowed')
        self.not_now = ConfigFile(self.path, 'not-now')
        self.disallowed = ConfigFile(self.path, 'disallowed')

    def refresh_not_now(self, cwd):
        result = []
        for path in self.not_now.lines:
            dirname = os.path.dirname(path)
            if path_is_under(cwd, dirname):
                result.append(path)
        self.not_now.write('w', '\n'.join(result))

    def _prompt_user(self, path):
        print(
            'aactivator will source {0} at {1}.'.format(
                ACTIVATE, path,
            ),
            file=sys.stderr,
        )
        while True:
            print('Acceptable? (y)es (n)o (N)ever: ', file=sys.stderr, end='')
            try:
                response = self.get_input()
            # Allow ^D to be "no"
            except EOFError:
                response = 'n'

            if response.startswith('N'):
                self.disallowed.append(path)
                print(
                    'aactivator will remember this: '
                    '~/.cache/aactivator/disallowed',
                    file=sys.stderr,
                )
                return False

            response = response.lower()
            if response.startswith('n'):
                self.not_now.append(path)
                return False
            elif response.startswith('y'):
                self.allowed.append(path)
                print(
                    'aactivator will remember this: '
                    '~/.cache/aactivator/allowed',
                    file=sys.stderr,
                )
                return True
            else:
                print("I didn't understand your response.", file=sys.stderr)
                print(file=sys.stderr)

    def find_allowed(self, path):
        self.refresh_not_now(path)
        return first(search_parent_paths(path), self.is_allowed)

    def is_allowed(self, path):
        if not os.path.exists(os.path.join(path, ACTIVATE)):
            return False
        elif path in self.disallowed.lines or path in self.not_now.lines:
            return False
        elif path in self.allowed.lines:
            return True
        else:
            return self._prompt_user(path)


def security_check(path):
    if not os.path.exists(path):
        return 'aactivator: File does not exist: ' + path
    insecure_path = insecure(path)
    if insecure_path is not None:
        return (
            'aactivator: Cowardly refusing to source {0} because writeable by others: {1}'
            .format(relpath(path), relpath(insecure_path))
        )


def aactivate(environ, path, pwd):
    state = state_path(environ, path)
    mkdirp(state, mode=0700)
    return ' &&\n'.join((
        '_aa_state=' + quote(state),

        # aliases (sh and zsh don't print the 'alias ' bit)
        r'''alias | sed 's/^\(alias \)\?/alias /' > "$_aa_state/alias"''',

        # environ vars (TIL: bash only modifies environ for subprocesses)
        r'''sh -c 'exec cat /proc/$$/environ' > "$_aa_state/environ"''',

        # now that we can rollback, we can provisionally call it active
        'export %s=%s' % (ENVIRONMENT_VARIABLE, quote(path)),

        # the meat: source the thing and ensure it succeeded
        'cd ' + quote(path),
        '-aa-source ' + ACTIVATE,
        '[ $_aa_ok ] || eval "$(aactivator deaactivate)"',
    )) + '\ncd ' + quote(pwd)


def deaactivate(current_env):
    path = current_env.get(ENVIRONMENT_VARIABLE)
    if not path:
        return  # nothing is active. all done!

    state = state_path(current_env, path)
    new_env = os.path.join(state, 'environ')
    try:
        new_env = env_parse_file(str(new_env))
    except EnvironmentError as error:
        print('Could not deaactivate, due to: %s' % error, file=sys.stderr)
        return 'unset ' + ENVIRONMENT_VARIABLE

    diff = env_diff(current_env, new_env)
    # it doesn't make sense to set/reset these three
    for var in ('_', 'PWD', 'OLDPWD'):
        diff.pop(var, None)

    # no '&&': failure to reset any part of the environ shouldn't derail the rest
    return '\n'.join(
        env_shell_commands(diff) +
        (
            '_aa_state=' + quote(state),
            'unalias -a',
            '-aa-source "$_aa_state/alias" &&',
            'rm -r $_aa_state',
        )
    )


def get_output(environ, cwd='.', get_input=sys.stdin.readline):
    try:
        cwd = os.path.realpath(cwd)
    except OSError as error:
        if error.errno == 2:  # no such file
            return ''
        else:
            raise
    config = ActivateConfig(environ, get_input)
    activate_path = config.find_allowed(cwd)
    activated_env = environ.get(ENVIRONMENT_VARIABLE)

    if activated_env == activate_path:
        return ''  # we have already activated the current environment

    result = []
    if activated_env:  # deactivate it
        result.append(deaactivate(environ))
    if activate_path:
        result.append(aactivate(environ, activate_path, cwd))
    return ' &&\n'.join(result)


def aactivator(args):
    env = os.environ
    if len(args) == 1:
        return get_output(env)
    elif len(args) == 2 and args[1] == 'init':
        return init(args[0])
    elif len(args) == 2 and args[1] == 'deaactivate':
        return deaactivate(env)
    elif len(args) == 3 and args[1] == 'security-check':
        exit(security_check(args[2]))
    else:
        return __doc__


def main():  # pragma: no cover
    from sys import argv
    print(aactivator(argv))


if __name__ == '__main__':
    try:
        exit(main())
    except KeyboardInterrupt:
        # Silence ^C (WEBCORE-1150)
        pass
