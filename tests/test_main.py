#!/usr/bin/env python
#
# Copyright 2013 Jose Fonseca
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU Lesser General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
import io
import difflib
import os.path
import subprocess


def run(cmd):
    p = subprocess.Popen(cmd)
    try:
        return p.wait()
    except KeyboardInterrupt:
        p.terminate()
        raise


def assert_no_diff(a, b):
    # Asserts no difference between two files
    a_lines = io.open(a, 'rt', encoding='UTF-8').readlines()
    b_lines = io.open(b, 'rt', encoding='UTF-8').readlines()
    diff_lines = difflib.unified_diff(a_lines, b_lines, fromfile=a, tofile=b)
    diff_lines = ''.join(diff_lines)
    assert diff_lines == ''


def test_main():
    # A fairly brittle end-to-end tests for the gprof2dot executable.
    # Runs gprof2dot in a subprocess and compares results against a
    # pre-created file. (Note that python's hash seed matters, since a lot
    # of the graph creation is iterating through dictionaries. Check tox.ini)
    test_subdir = os.path.join(os.getcwd(), 'tests/pstats')
    pstats_files = [f for f in os.listdir(test_subdir) if f.endswith('.pstats')]
    for filename in pstats_files:
        name, _ = os.path.splitext(filename)
        profile = os.path.join(test_subdir, filename)
        dot = os.path.join(test_subdir, name + '.dot')
        png = os.path.join(test_subdir, name + '.png')

        ref_dot = os.path.join(test_subdir, name + '.orig.dot')
        ref_png = os.path.join(test_subdir, name + '.orig.png')

        if run(['python', 'gprof2dot.py', '-o', dot, profile]) != 0:
            continue

        if run(['dot', '-Tpng', '-o', png, dot]) != 0:
            continue

        assert_no_diff(ref_dot, dot)
