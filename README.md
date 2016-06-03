aactivator
========

[![PyPI version](https://badge.fury.io/py/aactivator.svg)](https://pypi.python.org/pypi/aactivator)

`aactivator` is a simple tool that automatically sources ("activates") and
unsources a project's environment when entering and exiting it.

Key features of aactivator include:

* Prompting before sourcing previously-unseen directories.
* Refusing to source files that can be modified via others.
* First-class support for both `bash` and `zsh`.
* Well-tested, with integration tests applied to both supported shells.


## The aactivator interface

aactivator provides a simple interface for projects, via two files at the root
of the project:

* `.activate.sh`, which is sourced by the shell on enter.

  If working with Python virtualenvs, it usually makes the most sense to
  symlink `.activate.sh` to the `bin/activate` file inside your virtualenv.
  For example, `ln -s venv/bin/activate .activate.sh`.

* `.deactivate.sh`, which is sourced by the shell on enter.

  Typically, this is a one-line file that contains just `deactivate`, though it
  can be modified to suit your particular project.


## Installing into your shell

We recommend adding `aactivator` to your shell's config. It will stay out of
your way during regular usage, and you'll only ever notice it doing its job
when you `cd` into a project directory that supports aactivator.

You first need to install the `aactivator` binary somewhere on your system. You
have a few options:

1. Just copy the `aactivator.py` script somewhere on your system and make it
   executable (`chmod +x aactivator.py`). It has no dependencies besides the
   Python 2.7 standard library.

2. Install it via pip (`pip install aactivator`). You can install system-wide,
   to your home directory, or into a virtualenv (your preference).

3. Install the Debian package. This is the best option for system-wide
   automated installations, and gives you other niceties like a man-page.
   You can find pre-built Debian packages under the [Releases][releases] GitHub
   tab.

Once you have `aactivator` installed, you need to source it on login. To do
that, just add this line to your `.bashrc` (or `.zshrc` for zsh):

    eval "$(aactivator init)"

(You may need to prefix `aactivator` with the full path to the binary if you
didn't install it somewhere on your `$PATH`).


## Motivation

Automatically sourcing virtualenvs is a huge boon to large projects. It means
that you can directly execute tools like `py.test`, and also that the project
can register command-line tools (via setuptools' `console_scripts` entrypoint)
for use by contributors.


## Security considerations

We tried pretty hard to make this not a giant arbitrary-code-execution vector.
There are two main protections:

* `aactivator` asks before sourcing previously-unseen directories. You can
  choose between not sourcing once, never sourcing, or sourcing.

  You shouldn't choose to source projects whose code you don't trust. However,
  it's worth keeping in mind that the same consideration exists with running
  tests, building the virtualenv, or running any of that project's code.
  Sourcing the virtualenv is just as dangerous as any of these.

* `aactivator` refuses to source environment files which can be modified by
  others. It does this by recursing upwards from the current directory until
  hitting a filesystem boundary, and that the file (and all of its parents) can
  be modified by only you and `root`.


## Alternatives to aactivator

Some alternatives to `aactivator` already exist. For example:

* [kennethreitz's autoenv][autoenv]
* [codysoyland's virtualenv-auto-activate][codysoyland]
* [yourlabs's shell function][yourlabs]

These alternatives all have at least one of the following problems (compared to
aactivator):

* Don't ask (or remember) permission before sourcing directories
* Don't deactivate when leaving project directories
* Work by overriding the `cd` builtin (which means things like `popd` or other
  methods of changing directories don't work)
* Lack support for `zsh`
* Don't perform important security checks (see "Security" above)


[autoenv]: https://github.com/kennethreitz/autoenv
[codysoyland]: https://gist.github.com/codysoyland/2198913
[releases]: https://github.com/Yelp/aactivator/releases
[yourlabs]: http://blog.yourlabs.org/post/21015702927/automatic-virtualenv-activation
