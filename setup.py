from setuptools import setup

from aactivator import __version__


setup(
    name='aactivator',
    description=(
        'Automatically activate Python virtualenvs (and other environments).'
    ),
    url='https://github.com/Yelp/aactivator',
    version=__version__,
    author='Yelp',
    platforms='linux',
    classifiers=[
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
    ],
    py_modules=['aactivator'],
    entry_points={
        'console_scripts': [
            'aactivator = aactivator:main',
        ],
    },
)
