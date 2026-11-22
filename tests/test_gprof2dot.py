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

"""Regression tests: run gprof2dot on sample profiles and diff the output
against reference files.

Most references (*.orig.dot) are not committed.  A missing reference is
recorded from the current output and the test is skipped, so the first run
on a fresh checkout only records a baseline.  Pass --force-refs to
regenerate references.

Generated outputs are written to per-test temporary directories, so the
tests can run in parallel (pytest -n auto).
"""

import difflib
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import gprof2dot


TESTS_DIR = Path(__file__).resolve().parent

FORMATS = [
    "axe",
    "callgrind",
    "collapse",
    "hprof",
    "json",
    "perf",
    "prof",
    "pstats",
    "sleepy",
    "sysprof",
    "xperf",
    "dtrace",
]

FORMATS_COMPARE = [
    "axe",
    "callgrind",
    "pstats",
]

HAVE_DOT = shutil.which('dot') is not None


def run_gprof2dot(*args):
    try:
        gprof2dot.main([str(arg) for arg in args])
    except SystemExit as ex:
        if ex.code not in (None, 0):
            pytest.fail('gprof2dot exited with status %r' % (ex.code,), pytrace=False)


def render(dot, png):
    if HAVE_DOT:
        subprocess.run(['dot', '-Tpng', '-o', str(png), str(dot)], check=True)


def check_reference(actual, ref, force_refs):
    """Diff actual against ref, recording ref when missing or forced."""
    if force_refs or not ref.exists():
        shutil.copy(actual, ref)
        pytest.skip('reference recorded: %s' % ref.relative_to(TESTS_DIR))

    ref_lines = ref.read_text(encoding='UTF-8').splitlines(keepends=True)
    actual_lines = actual.read_text(encoding='UTF-8').splitlines(keepends=True)
    if ref_lines != actual_lines:
        diff = ''.join(difflib.unified_diff(
            ref_lines, actual_lines, fromfile=str(ref), tofile=str(actual)))
        pytest.fail('output differs from reference:\n' + diff, pytrace=False)


def check_graph(dot, ref_dot, force_refs):
    """Render the generated graph, and check it against the reference."""
    png = dot.with_suffix('.png')
    render(dot, png)
    if (force_refs or not ref_dot.exists()) and png.exists():
        shutil.copy(png, ref_dot.with_suffix('.png'))
    check_reference(dot, ref_dot, force_refs)


# Sorted, so that every pytest-xdist worker collects the same tests in the
# same order.
FORMAT_CASES = sorted(
    (fmt, profile)
    for fmt in FORMATS
    for profile in (TESTS_DIR / fmt).glob('*.' + fmt)
)


@pytest.mark.parametrize(
    'fmt,profile', FORMAT_CASES,
    ids=['%s-%s' % (fmt, profile.stem) for fmt, profile in FORMAT_CASES])
def test_format(fmt, profile, tmp_path, force_refs):
    dot = tmp_path / (profile.stem + '.dot')
    run_gprof2dot('-f', fmt, '-o', dot, profile)
    check_graph(dot, profile.with_name(profile.stem + '.orig.dot'), force_refs)


COMPARE_CASES = sorted(
    (fmt, case_dir)
    for fmt in FORMATS_COMPARE
    for case_dir in (TESTS_DIR / 'compare' / fmt).iterdir()
    if case_dir.is_dir()
)


@pytest.mark.parametrize(
    'fmt,case_dir', COMPARE_CASES,
    ids=['%s-%s' % (fmt, case_dir.name) for fmt, case_dir in COMPARE_CASES])
def test_compare(fmt, case_dir, tmp_path, force_refs):
    ext = '.txt' if fmt == 'axe' else '.' + fmt
    name1 = case_dir.name + '1'
    name2 = case_dir.name + '2'
    dot = tmp_path / (name1 + '.dot')
    run_gprof2dot('-f', fmt, '-o', dot, '--compare',
                  case_dir / (name1 + ext), case_dir / (name2 + ext))
    check_graph(dot, case_dir / (name1 + '.orig.dot'), force_refs)


# Command line option variants, checked against <stem>.<name>.orig.dot next to
# the (first) input.
OPTION_CASES = sorted([
    ('callgrind', 'xapian', 'strip-wrap', ['-s', '-w']),
    ('collapse', 'synapse', 'callstacks', ['--total=callstacks']),
    ('dtrace', 'go', 'callstacks', ['--total=callstacks']),
    ('perf', 'glxgears', 'callstacks', ['--total=callstacks']),
    ('perf', 'glxgears', 'path', ['-p', 'libGL']),
    ('perf', 'glxgears', 'print-skew', ['-c', 'print', '--skew=0.5']),
    ('perf', 'glxgears', 'selftime', ['--color-nodes-by-selftime']),
    ('pstats', 'memtrail', 'labels', ['--node-label=self-time',
                                      '--node-label=total-time',
                                      '--time-format=%.3fs',
                                      '--show-samples']),
    ('pstats', 'memtrail', 'leaf', ['-l', '*read_fmt', '--depth=2']),
    ('pstats', 'memtrail', 'path', ['-p', 'memtrail']),
    ('pstats', 'memtrail', 'root-depth', ['-z', '*:main', '--depth=1']),
])


@pytest.mark.parametrize(
    'fmt,stem,name,args', OPTION_CASES,
    ids=['%s-%s-%s' % case[:3] for case in OPTION_CASES])
def test_options(fmt, stem, name, args, tmp_path, force_refs):
    profile = TESTS_DIR / fmt / (stem + '.' + fmt)
    dot = tmp_path / ('%s.%s.dot' % (stem, name))
    run_gprof2dot('-f', fmt, '-o', dot, *args, profile)
    check_graph(dot, profile.with_name('%s.%s.orig.dot' % (stem, name)), force_refs)


# --compare option variants, checked against <dir>1.<name>.orig.dot.
COMPARE_OPTION_CASES = [
    ('callgrind', 'test', 'color-by-difference', ['--compare-color-by-difference']),
    ('callgrind', 'test', 'only-slower', ['--compare-only-slower']),
    ('callgrind', 'unmatched', 'strip-wrap', ['-s', '-w']),
]


@pytest.mark.parametrize(
    'fmt,case,name,args', COMPARE_OPTION_CASES,
    ids=['%s-%s-%s' % case[:3] for case in COMPARE_OPTION_CASES])
def test_compare_options(fmt, case, name, args, tmp_path, force_refs):
    case_dir = TESTS_DIR / 'compare' / fmt / case
    ext = '.' + fmt
    dot = tmp_path / ('%s1.%s.dot' % (case, name))
    run_gprof2dot('-f', fmt, '-o', dot, '--compare', *args,
                  case_dir / (case + '1' + ext), case_dir / (case + '2' + ext))
    check_graph(dot, case_dir / ('%s1.%s.orig.dot' % (case, name)), force_refs)


def test_list_functions_dump(capfd):
    # The dump includes object addresses, so only smoke test it.
    profile = TESTS_DIR / 'pstats' / 'memtrail.pstats'
    capfd.readouterr()
    run_gprof2dot('-f', 'pstats', '--list-functions=%*:main', profile)
    err = capfd.readouterr().err
    assert 'memtrail:950:main' in err
    assert 'called:=' in err


def test_stdin(monkeypatch, tmp_path):
    profile = TESTS_DIR / 'collapse' / 'synapse.collapse'
    expected = tmp_path / 'file.dot'
    run_gprof2dot('-f', 'collapse', '-o', expected, profile)
    actual = tmp_path / 'stdin.dot'
    with open(profile, encoding='utf-8-sig') as stdin:
        monkeypatch.setattr(sys, 'stdin', stdin)
        run_gprof2dot('-f', 'collapse', '-o', actual)
    assert actual.read_text(encoding='UTF-8') == expected.read_text(encoding='UTF-8')


def test_list_functions(capfd, tmp_path, force_refs):
    profile = TESTS_DIR / 'pstats' / 'memtrail.pstats'
    capfd.readouterr()
    for selector in ("+", "execfile", "*execfile", "*:execfile", "*parse", "*parse_*"):
        run_gprof2dot('-f', 'pstats', '--list-functions=' + selector, profile)
    actual = tmp_path / 'function-list.txt'
    actual.write_text(capfd.readouterr().err, encoding='UTF-8')
    check_reference(actual, TESTS_DIR / 'pstats' / 'function-list.orig.txt', force_refs)


# Functions sharing a name (foo in a.c and b.c) must be kept apart, both when
# selected by --root and when matched up by --compare.
DUPNAMES_DIR = TESTS_DIR / 'collapse'
DUPNAMES_CASES = [
    ('dupnames-root', ['--root=foo', DUPNAMES_DIR / 'dupnames.collapse']),
    ('dupnames-compare-root', ['--compare', '--root=foo',
                               DUPNAMES_DIR / 'dupnames.collapse',
                               DUPNAMES_DIR / 'dupnames2.collapse']),
]


@pytest.mark.parametrize(
    'name,args', DUPNAMES_CASES, ids=[name for name, args in DUPNAMES_CASES])
def test_dupnames(name, args, tmp_path, force_refs):
    actual = tmp_path / (name + '.txt')
    run_gprof2dot('-f', 'collapse', '-e0', '-n0', '-o', actual, *args)
    check_reference(actual, DUPNAMES_DIR / (name + '.orig.txt'), force_refs)
