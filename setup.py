import io
from setuptools import setup


with io.open('VERSION') as f:
    version = f.read().strip()


setup(
    name='aactivator',
    description=(
        'Automatically activate Python virtualenvs (and other environments).'
    ),
    url='https://github.com/Yelp/aactivator',
    version=version,
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
