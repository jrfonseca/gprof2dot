#!/usr/bin/env python3
#
# Copyright 2013-2017 Jose Fonseca
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
from   subprocess import PIPE
import shutil


assert sys.version_info[0] >= 3


formats = [
    "axe",
    "callgrind",
    "collapse",
    "hprof",
    "json",
    "oprofile",
    "perf",
    "prof",
    "pstats",
    "sleepy",
    "sysprof",
    "xperf",
    "dtrace",
]
formats_compare = [
    "axe",
    "callgrind",
    "pstats"
]


NB_RUN_FAILURES = 0
NB_DIFF_FAILURES = 0


def run(cmd, stderr=None):
    global NB_RUN_FAILURES
    retcde = 0
    sys.stdout.write(' '.join(cmd) + '\n')
    sys.stdout.flush()
    p = subprocess.Popen(cmd, stderr=stderr)
    try:
        retcde = p.wait()
        if retcde !=0:
            print("Run failed and returned %d" % retcde)
            sys.stdout.flush()
            NB_RUN_FAILURES += 1
    except KeyboardInterrupt:
        p.terminate()
        raise
    return retcde


coverage_append = False

def run_gprof2dot(args, stderr=None):
    global coverage_append
    cmd = [options.python]
    if options.coverage:
        cmd += ['-m', 'coverage', 'run']
        if coverage_append:
            cmd += ['-a']
        else:
            coverage_append = True
        cmd += ['--']
    cmd += [options.gprof2dot]
    cmd += args
    return run(cmd, stderr=stderr)


def diff(a, b):
    global NB_DIFF_FAILURES
    a_lines = open(a, 'rt', encoding='UTF-8').readlines()
    b_lines = open(b, 'rt', encoding='UTF-8').readlines()
    diff_lines = difflib.unified_diff(a_lines, b_lines, fromfile=a, tofile=b)

    diff_txt = ''.join(diff_lines)
    if len(diff_txt) > 0:
        NB_DIFF_FAILURES += 1
        sys.stdout.write("Non empty diff for files %s and %s" %(a,b))
    sys.stdout.write(diff_txt)


def main():
    """Main program."""

    global options
    global formats
    global NB_RUN_FAILURES, NB_DIFF_FAILURES

    test_dir = os.path.dirname(os.path.abspath(__file__))

    optparser = optparse.OptionParser(
        usage="\n\t%prog [options] [format] ...")
    optparser.add_option(
        '-p', '--python', metavar='PATH',
        type="string", dest="python", default=sys.executable,
        help="path to python executable [default: %default]")
    optparser.add_option(
        '-g', '--gprof2dot', metavar='PATH',
        type="string", dest="gprof2dot", default=os.path.abspath(os.path.join(test_dir, os.path.pardir, 'gprof2dot.py')),
        help="path to gprof2dot.py script [default: %default]")
    optparser.add_option(
        '-f', '--force',
        action="store_true",
        dest="force", default=False,
        help="force reference generation")
    optparser.add_option(
        '-c', '--coverage',
        action="store_true",
        dest="coverage", default=False,
        help="code coverage")

    # Added this to avoid failing the test when a (hopefully small) number of formats
    # result in error. This allows some flexibility in CI testing.
    optparser.add_option(
        '--max-acceptable',
        type=int,
        dest="max_acceptable",
        help="max acceptable errors before we return an errcode and fail the test")

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

                if run_gprof2dot(['-f', format, '-o', dot, profile]) != 0:
                    continue

                if run(['dot', '-Tpng', '-o', png, dot]) != 0:
                    continue

                if options.force or not os.path.exists(ref_dot):
                    shutil.copy(dot, ref_dot)
                    shutil.copy(png, ref_png)
                else:
                    diff(ref_dot, dot)

    for format_compare in formats_compare:
        subdir = os.path.join(test_dir, 'compare', format_compare)
        for dirname in os.listdir(subdir):
            test_subdir = os.path.join(subdir, dirname)
            name1 = dirname + '1.'
            name2 = dirname + '2.'
            filename1 = name1 + 'txt' if format_compare == 'axe' else name1 + format_compare
            filename2 = name2 + 'txt' if format_compare == 'axe' else name2 + format_compare

            sys.stdout.write(filename1 + '\n')

            profile1 = os.path.join(test_subdir, filename1)
            profile2 = os.path.join(test_subdir, filename2)
            dot = os.path.join(test_subdir, name1 + '.dot')
            png = os.path.join(test_subdir, name1 + '.png')

            ref_dot = os.path.join(test_subdir, name1 + '.orig.dot')
            ref_png = os.path.join(test_subdir, name1 + '.orig.png')

            if run_gprof2dot(['-f', format_compare, '-o', dot, '--compare', profile1, profile2]) != 0:
                continue

            if run(['dot', '-Tpng', '-o', png, dot]) != 0:
                continue

            if options.force or not os.path.exists(ref_dot):
                shutil.copy(dot, ref_dot)
                shutil.copy(png, ref_png)
            else:
                diff(ref_dot, dot)

    # test the --list-functions flag only for pstats format
    profile = os.path.join(test_dir, 'pstats', 'memtrail.pstats')
    genfileNm = os.path.join(test_dir, 'pstats', 'function-list.testgen.txt')
    outfile = open(genfileNm, "w")
    for flagVal in ("+", "execfile", "*execfile", "*:execfile", "*parse", "*parse_*"):
        run_gprof2dot(['-f', "pstats", "--list-functions="+flagVal, profile], stderr=outfile)

    outfile.close()

    diff(genfileNm, os.path.join(test_dir, 'pstats', 'function-list.orig.txt'))

    if options.coverage:
        if os.environ.get('GITHUB_ACTIONS', 'false') == 'true':
            run([options.python, '-m', 'coverage', 'xml'])
        else:
            run([options.python, '-m', 'coverage', 'html'])

    if NB_RUN_FAILURES or NB_DIFF_FAILURES:
        print("Nb runs ending in error: %d" % NB_RUN_FAILURES)
        print("Nb diffs showing a difference: %d" % NB_DIFF_FAILURES)
        if (options.max_acceptable is not None
             and NB_RUN_FAILURES + NB_DIFF_FAILURES > options.max_acceptable ):
            print("Too many errors: returning non-zero code")
            sys.exit(1)


if __name__ == '__main__':
    main()
