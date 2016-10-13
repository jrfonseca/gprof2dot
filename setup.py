#!/usr/bin/env python
#
# The purpose of this script is to enable uploading gprof2dot.py to the Python
# Package Index, which can be easily done by doing:
#
#   python setup.py register
#   python setup.py sdist upload
#
# See also:
# - https://code.google.com/archive/p/jrfonseca/issues/19
# - https://docs.python.org/2/distutils/packageindex.html
#

import sys
from setuptools import setup

setup(
    name='gprof2dot',
    version='2016.10.13',
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
)
