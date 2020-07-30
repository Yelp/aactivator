#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""\
Usage: eval "$(aactivator init)"

aactivator is a script for automatically sourcing environments in an interactive shell.
The interface for using this is two files:

    - .activate.sh: when sourced, this file activates your environment
    - .deactivate.sh: when sourced, this file deactivates your environment

A typical setup in a python project:

    $ ln -vs venv/bin/activate .activate.sh
    $ echo deactivate > .deactivate.sh

If an environment is already active it will not be re-activated.
If a different project is activated, the previous project will be deactivated beforehand.

aactivator will ask before automatically sourcing environments, and optionally
remember your answer. You can later adjust your per-project preferences in the
~/.cache/aactivator/ directory.

see also: https://github.com/Yelp/aactivator
"""
from __future__ import absolute_import
from __future__ import print_function
from __future__ import unicode_literals

import io
import os.path
import stat
import sys
from os.path import relpath
from pipes import quote


ENVIRONMENT_VARIABLE = 'AACTIVATOR_ACTIVE'
ACTIVATE = '.activate.sh'
DEACTIVATE = '.deactivate.sh'

__version__ = '1.0.1'


def init(arg0):
    arg0 = os.path.realpath(arg0)
    cmd = 'if [ -x {exe} ]; then  eval "`{exe}`"; fi'.format(exe=arg0)
    return '''\
export AACTIVATOR_VERSION={version}
alias aactivator={arg0}
unset {varname}
if [ "$ZSH_VERSION" ]; then
    precmd_aactivator() {{ {cmd}; }}
    if ! [ "${{precmd_functions[(r)precmd_aactivator]}}" ]; then
        precmd_functions=(precmd_aactivator $precmd_functions)
    fi
else
    if ! ( echo "$PROMPT_COMMAND" | grep -Fq '{cmd}' ); then
        PROMPT_COMMAND='{cmd}; '"$PROMPT_COMMAND"
    fi
fi'''.format(version=__version__, arg0=arg0, cmd=cmd, varname=ENVIRONMENT_VARIABLE)


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
    pathstat = os.stat(path).st_mode
    # Directories with a sticky bit are always acceptable.
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
    path = os.path.abspath(path)
    original_fs_id = fs_id = get_filesystem_id(path)
    previous_path = None
    while original_fs_id == fs_id and path != previous_path:
        yield path
        previous_path = path
        path = os.path.dirname(path)
        fs_id = get_filesystem_id(path)


def error_command(message):
    return 'echo %s >&2' % quote('aactivator: ' + message)


def mkdirp(path):
    try:
        os.makedirs(path)
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


def user_cache_dir(env):
    # stolen from pip.utils.appdirs.user_cache_dir
    # expanduser doesn't take an env argument -.-
    from os.path import expanduser
    orig, os.environ = os.environ, env
    try:
        return expanduser(env.get('XDG_CACHE_HOME', '~/.cache'))
    finally:
        os.environ = orig


class ActivateConfig(object):

    def __init__(self, env, get_input):
        self.env = env
        self.get_input = get_input
        self.path = os.path.join(user_cache_dir(self.env), 'aactivator')
        self.allowed = ConfigFile(self.path, 'allowed')
        self.not_now = ConfigFile(self.path, 'not-now')
        self.disallowed = ConfigFile(self.path, 'disallowed')

    def refresh_not_now(self, pwd):
        result = []
        for path in self.not_now.lines:
            dirname = os.path.dirname(path)
            if path_is_under(pwd, dirname):
                result.append(path)
        self.not_now.write('w', '\n'.join(result))

    def _prompt_user(self, path):
        print(
            'aactivator will source {0} and {1} at {2}.'.format(
                ACTIVATE, DEACTIVATE, path,
            ),
            file=sys.stderr,
        )
        while True:
            print('Acceptable? (y)es (n)o (N)ever: ', file=sys.stderr, end='')
            sys.stderr.flush()
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

    def is_allowed(self, path, _getuid=os.getuid):
        activate = os.path.join(path, ACTIVATE)
        if not os.path.exists(activate):
            return False
        elif os.stat(activate).st_uid != _getuid():
            # If we do not own this path, short circuit on activating
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


def command_for_path(cmd, path, pwd):
    if path == pwd:
        return cmd
    else:
        return ' &&\n'.join((
            'OLDPWD_bak="$OLDPWD"',
            'cd ' + quote(path),
            cmd,
            'cd "$OLDPWD_bak"',
            'cd ' + quote(pwd),
            'unset OLDPWD_bak',
        ))


def aactivate(path, pwd):
    return command_for_path(
        ' &&\n'.join((
            'aactivator security-check ' + ACTIVATE,
            'source ./' + ACTIVATE,
            'export %s=%s' % (ENVIRONMENT_VARIABLE, quote(path)),
        )),
        path,
        pwd,
    )


def deaactivate(path, pwd):
    unset = 'unset ' + ENVIRONMENT_VARIABLE
    deactivate_path = os.path.join(path, DEACTIVATE)

    if os.path.exists(deactivate_path):
        return command_for_path(
            ' &&\n'.join((
                'aactivator security-check ' + DEACTIVATE,
                'source ./' + DEACTIVATE,
            )) + '\n' + unset,
            path,
            pwd,
        )
    else:
        return ' &&\n'.join((
            unset,
            error_command('Cannot deactivate. File missing: {0}'.format(deactivate_path))
        ))


def get_output(environ, pwd='.', get_input=sys.stdin.readline, arg0='/path/to/aactivator'):
    try:
        pwd = os.path.realpath(pwd)
    except OSError as error:
        if error.errno == 2:  # no such file
            return ''
        else:
            raise
    config = ActivateConfig(environ, get_input)
    activate_path = config.find_allowed(pwd)
    result = []

    if environ.get('AACTIVATOR_VERSION') == __version__:
        activated_env = environ.get(ENVIRONMENT_VARIABLE)
    else:
        result.append(init(arg0))
        activated_env = None

    if activated_env != activate_path:  # did we already activate the current environment?
        if activated_env:  # deactivate it
            result.append(deaactivate(activated_env, pwd))
        if activate_path:
            result.append(aactivate(activate_path, pwd))
    return ' &&\n'.join(result)


def aactivator(args, env):
    if len(args) == 1:
        return get_output(env, arg0=args[0])
    elif len(args) == 2 and args[1] == 'init':
        return init(args[0])
    elif len(args) == 3 and args[1] == 'security-check':
        exit(security_check(args[2]))
    else:
        return __doc__ + '\nVersion: ' + __version__


def main():
    try:
        print(aactivator(tuple(sys.argv), os.environ.copy()))
    except KeyboardInterrupt:  # pragma: no cover
        # Silence ^C
        pass


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        # Silence ^C
        pass
