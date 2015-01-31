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


import difflib
import optparse
import os.path
import sys
import subprocess
import shutil


if sys.version_info[0] >= 3:
    PYTHON_3 = True
else:
    PYTHON_3 = False


formats = [
    "axe",
    "callgrind",
    "hprof",
    "json",
    "oprofile",
    "perf",
    "prof",
    "pstats",
    "sleepy",
    "sysprof",
    "xperf",
]


def run(cmd):
    sys.stderr.flush()
    sys.stdout.write(' '.join(cmd) + '\n')
    sys.stdout.flush()
    p = subprocess.Popen(cmd)
    try:
        return p.wait()
    except KeyboardInterrupt:
        p.terminate()
        raise


def diff(a, b):
    if PYTHON_3:
        a_lines = open(a, 'rt', encoding='UTF-8').readlines()
        b_lines = open(b, 'rt', encoding='UTF-8').readlines()
    else:
        a_lines = open(a, 'rt').readlines()
        b_lines = open(b, 'rt').readlines()
    diff_lines = difflib.unified_diff(a_lines, b_lines, fromfile=a, tofile=b)
    sys.stdout.write(''.join(diff_lines))


def main():
    """Main program."""

    global formats

    test_dir = os.path.dirname(os.path.abspath(__file__))

    optparser = optparse.OptionParser(
        usage="\n\t%prog [options] [format] ...")
    optparser.add_option(
        '-p', '--python', metavar='PATH',
        type="string", dest="python", default=sys.executable,
        help="path to python executable [default: %default]")
    optparser.add_option(
        '-g', '--gprof2dot', metavar='PATH',
        type="string", dest="gprof2dot", default=os.path.join(test_dir, os.path.pardir, 'gprof2dot.py'),
        help="path to gprof2dot.py script [default: %default]")
    optparser.add_option(
        '-f', '--force',
        action="store_true",
        dest="force", default=False,
        help="force reference generation")
    (options, args) = optparser.parse_args(sys.argv[1:])

    if len(args):
        formats = args

    for format in formats:
        test_subdir = os.path.join(test_dir, format)
        for filename in os.listdir(test_subdir):
            name, ext = os.path.splitext(filename)
            if ext == '.' + format:
                sys.stdout.write(filename + '\n')

                profile = os.path.join(test_subdir, filename)
                dot = os.path.join(test_subdir, name + '.dot')
                png = os.path.join(test_subdir, name + '.png')
                
                ref_dot = os.path.join(test_subdir, name + '.orig.dot')
                ref_png = os.path.join(test_subdir, name + '.orig.png')

                if run([ options.python, options.gprof2dot, '-f', format, '-o', dot, profile]) != 0:
                    continue

                if run(['dot', '-Tpng', '-o', png, dot]) != 0:
                    continue

                if options.force or not os.path.exists(ref_dot):
                    shutil.copy(dot, ref_dot)
                    shutil.copy(png, ref_png)
                else:
                    diff(ref_dot, dot)


if __name__ == '__main__':
    main()
