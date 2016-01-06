#!/usr/bin/env python
#
# The purpose of this script is to enable uploading gprof2dot.py to the Python
# Package Index, which can be easily done by doing:
#
#   python setup.py register
#   python setup.py sdist upload
#
# See also:
# - https://code.google.com/p/jrfonseca/issues/detail?id=19
# - http://docs.python.org/2/distutils/packageindex.html
#
# Original version was written by Jose Fonseca; see
# https://github.com/jrfonseca/gprof2dot

import sys
from setuptools import setup

setup(
    name='yelp-gprof2dot',
    version='1.0.1',
    author='Yelp Performance Team',
    url='https://github.com/Yelp/gprof2dot',
    description="Generate a dot graph from the output of python profilers.",
    long_description="""
        gprof2dot.py is a Python script to convert the output from python
        profilers (anything in pstats format) into a dot graph. It is a
        fork of the original gprof2dot script to extend python features.
        """,
    license="LGPL",

    py_modules=['gprof2dot'],
    entry_points=dict(console_scripts=['gprof2dot=gprof2dot:main']),
)
