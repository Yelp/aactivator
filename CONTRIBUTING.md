Contributing to aactivator
========

`aactivator` is primarily developed by [Yelp](https://yelp.github.io/), but
contributions are welcome from everyone!

Code is reviewed using GitHub pull requests. To make a contribution, you should:

1. Fork the GitHub repository
2. Push code to a branch on your fork
3. Create a pull request and wait for it to be reviewed

We aim to have all aactivator behavior covered by tests. If you make a change in
behavior, please add a test to ensure it doesn't regress. We're also happy to
help with suggestions on testing!


## Releasing new versions

`aactivator` uses [semantic versioning](http://semver.org/). If you're making a
contribution, please don't bump the version number yourself—we'll take care of
that after merging!

The process to release a new version is:

1. Update the version in `aactivator.py`
2. Update the Debian changelog with `dch -v {new version}`.
3. Commit the changes and tag the commit like `v1.0.0`.
4. `git push --tags origin master`
5. Run `python setup.py bdist_wheel`
6. Run `twine upload --skip-existing dist/*.whl` to upload the new version to
   PyPI
7. Run `make builddeb-docker`
8. Upload the resulting Debian package to a new [GitHub
   release](https://github.com/Yelp/aactivator/releases)
