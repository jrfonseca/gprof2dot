#!/usr/bin/env python3
#
# The purpose of this script is to enable uploading gprof2dot.py to the Python
# Package Index, which can be easily done by doing:
#
#   python3 setup.py sdist upload
#
# See also:
# - https://packaging.python.org/distributing/
# - https://docs.python.org/3/distutils/packageindex.html
#

from setuptools import setup

setup(
    name='gprof2dot',
    version='2021.02.21',
    author='Jose Fonseca',
    author_email='jose.r.fonseca@gmail.com',
    url='https://github.com/jrfonseca/gprof2dot',
    description="Generate a dot graph from the output of several profilers.",
    long_description="""
        gprof2dot.py is a Python script to convert the output from many
        profilers into a dot graph.
        """,
    license="LGPL",

    py_modules=['gprof2dot'],
    entry_points=dict(console_scripts=['gprof2dot=gprof2dot:main']),

    # https://pypi.python.org/pypi?%3Aaction=list_classifiers
    classifiers=[
        'Development Status :: 6 - Mature',

        'Environment :: Console',

        'Intended Audience :: Developers',

        'Operating System :: OS Independent',

        'License :: OSI Approved :: GNU Lesser General Public License v3 or later (LGPLv3+)',

        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',

        'Topic :: Software Development',
    ],
)
