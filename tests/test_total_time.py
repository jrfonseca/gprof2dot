#!/usr/bin/env python3
#
# Unit tests for the --show-total-time option.
#
# Run with:  python3 -m unittest discover -s tests -p 'test_*.py'

import io
import os
import re
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(TEST_DIR))

import gprof2dot  # noqa: E402
from gprof2dot import DotWriter, Profile, Function, TOTAL_TIME, TIME, themes, fmtduration  # noqa: E402


PSTATS_FILE = os.path.join(TEST_DIR, 'pstats', 'memtrail.pstats')
TOTAL_TIME_LINE = re.compile(r'^\t"\[total time\]" \[(?P<attrs>.*)\];$', re.M)


def total_time_lines(dot):
    return TOTAL_TIME_LINE.findall(dot)


def node_statement_ids(dot):
    """Return the ids of all node statements, in order, excluding attribute defaults."""
    ids = []
    for line in dot.splitlines():
        m = re.match(r'^\t("(?:[^"\\]|\\.)*"|\w+) \[', line)
        if m and m.group(1) not in ('graph', 'node', 'edge') and ' -> ' not in line:
            ids.append(m.group(1))
    return ids


def make_profile(total_time=None, nfunctions=2):
    profile = Profile()
    profile[TIME] = 0.0
    if total_time is not None:
        profile[TOTAL_TIME] = total_time
    for i in range(nfunctions):
        f = Function(i, 'func%d' % i)
        f[TIME] = 1.0
        f[TOTAL_TIME] = 1.0
        f.weight = 0.5
        profile.functions[i] = f
    return profile


class FmtDurationTests(unittest.TestCase):

    def test_three_significant_digits_with_unit(self):
        cases = [
            (13.120819960999992, '13.1 s'),
            (1.0, '1.00 s'),
            (1.23456, '1.23 s'),
            (123.456, '123 s'),
            (1234.5, '1230 s'),
            (0.5, '500 ms'),
            (0.123456, '123 ms'),
            (0.0123456, '12.3 ms'),
            (0.001, '1.00 ms'),
            (0.000482, '482 \u00b5s'),
            (7.5e-6, '7.50 \u00b5s'),
            (2.5e-9, '2.50 ns'),
            (1e-12, '0.00100 ns'),
            (0.0, '0 s'),
        ]
        for seconds, expected in cases:
            with self.subTest(seconds=seconds):
                self.assertEqual(fmtduration(seconds), expected)

    def test_rounding_promotes_unit(self):
        # 999.6 ms rounds to 1000 ms, which must be shown as 1.00 s.
        self.assertEqual(fmtduration(0.9996), '1.00 s')
        self.assertEqual(fmtduration(0.0009996), '1.00 ms')
        # Just below the rounding boundary stays in the smaller unit.
        self.assertEqual(fmtduration(0.9994), '999 ms')

    def test_edge_values(self):
        self.assertEqual(fmtduration(-2.5), '-2.50 s')
        self.assertEqual(fmtduration(float('inf')), 'inf')
        self.assertEqual(fmtduration(float('nan')), 'nan')


class DotWriterTotalTimeTests(unittest.TestCase):

    def render(self, profile, show_total_time, theme='color'):
        out = io.StringIO()
        err = io.StringIO()
        writer = DotWriter(out)
        writer.show_total_time = show_total_time
        with redirect_stderr(err):
            writer.graph(profile, themes[theme])
        return out.getvalue(), err.getvalue()

    def test_disabled_by_default(self):
        self.assertFalse(DotWriter(io.StringIO()).show_total_time)
        dot, err = self.render(make_profile(total_time=4.5), show_total_time=False)
        self.assertEqual(total_time_lines(dot), [])
        self.assertEqual(err, '')

    def test_node_emitted_with_formatted_value(self):
        dot, err = self.render(make_profile(total_time=13.120819960999992), show_total_time=True)
        lines = total_time_lines(dot)
        self.assertEqual(len(lines), 1)
        attrs = lines[0]
        self.assertIn('label="Total time\\n13.1 s"', attrs)
        self.assertIn('tooltip="total running time of the program"', attrs)
        self.assertEqual(err, '')

    def test_node_uses_hottest_theme_colors(self):
        theme = themes['color']
        dot, _ = self.render(make_profile(total_time=1.0), show_total_time=True)
        attrs = total_time_lines(dot)[0]
        writer = DotWriter(io.StringIO())
        self.assertIn('color=%s' % writer.escape(writer.color(theme.node_bgcolor(1.0))), attrs)
        self.assertIn('fontcolor=%s' % writer.escape(writer.color(theme.node_fgcolor(1.0))), attrs)
        self.assertIn('fontsize="%.2f"' % theme.node_fontsize(1.0), attrs)

    def test_node_comes_first_and_does_not_collide_with_functions(self):
        profile = make_profile(total_time=2.0, nfunctions=3)
        dot, _ = self.render(profile, show_total_time=True)
        ids = node_statement_ids(dot)
        self.assertEqual(ids[0], '"[total time]"')
        self.assertEqual(ids[1:], ['0', '1', '2'])
        self.assertEqual(ids.count('"[total time]"'), 1)
        # Function id 0 must keep its own label, not be merged with the total node.
        self.assertRegex(dot, r'(?m)^\t0 \[.*label=func0[,\]]')

    def test_function_named_like_node_id_is_distinct(self):
        # A function whose *name* equals the node id text still gets its own numeric id.
        profile = make_profile(total_time=2.0, nfunctions=1)
        profile.functions[0].name = '[total time]'
        dot, _ = self.render(profile, show_total_time=True)
        self.assertEqual(len(total_time_lines(dot)), 1)
        self.assertRegex(dot, r'(?m)^\t0 \[.*label="\[total time\]"')

    def test_missing_total_time_warns_and_skips(self):
        dot, err = self.render(make_profile(total_time=None), show_total_time=True)
        self.assertEqual(total_time_lines(dot), [])
        self.assertIn('warning: total time is not available', err)
        # Graph is still complete and well formed.
        self.assertTrue(dot.startswith('digraph {\n'))
        self.assertTrue(dot.rstrip().endswith('}'))

    def test_print_theme_unfilled_style(self):
        dot, err = self.render(make_profile(total_time=1.0), show_total_time=True, theme='print')
        self.assertEqual(len(total_time_lines(dot)), 1)
        self.assertEqual(err, '')


class CommandLineTotalTimeTests(unittest.TestCase):

    def setUp(self):
        # main() assigns module globals from the options; restore them afterwards.
        self.saved_globals = (gprof2dot.timeFormat, gprof2dot.totalMethod)
        self.tmpdir = tempfile.TemporaryDirectory()
        self.out = os.path.join(self.tmpdir.name, 'out.dot')
        import pstats
        self.expected_total = pstats.Stats(PSTATS_FILE).total_tt

    def tearDown(self):
        gprof2dot.timeFormat, gprof2dot.totalMethod = self.saved_globals
        self.tmpdir.cleanup()

    def run_main(self, *args):
        err = io.StringIO()
        with redirect_stderr(err):
            gprof2dot.main(['-f', 'pstats', '-o', self.out] + list(args) + [PSTATS_FILE])
        with open(self.out, encoding='utf-8') as f:
            return f.read(), err.getvalue()

    def test_pstats_parser_records_cprofile_total(self):
        profile = gprof2dot.PstatsParser(PSTATS_FILE).parse()
        self.assertAlmostEqual(profile[TOTAL_TIME], self.expected_total, places=9)

    def test_default_output_has_no_total_time_node(self):
        dot, _ = self.run_main()
        self.assertEqual(total_time_lines(dot), [])

    def test_flag_adds_single_node_with_cprofile_total(self):
        dot, err = self.run_main('--show-total-time')
        lines = total_time_lines(dot)
        self.assertEqual(len(lines), 1)
        expected_label = 'Total time\\n' + fmtduration(self.expected_total)
        self.assertIn('label="%s"' % expected_label, lines[0])
        self.assertIn('13.1 s', lines[0])
        self.assertEqual(err, '')

    def test_node_label_independent_of_time_format(self):
        # --time-format applies to per-function times, not to the total time node.
        dot, _ = self.run_main('--show-total-time', '--time-format', '%.5f')
        self.assertIn('label="Total time\\n13.1 s"', total_time_lines(dot)[0])

    def test_prof_format_also_shows_total(self):
        prof = os.path.join(TEST_DIR, 'prof', 'dan.skorupski.prof')
        err = io.StringIO()
        with redirect_stderr(err):
            gprof2dot.main(['-f', 'prof', '-o', self.out, '--show-total-time', prof])
        with open(self.out, encoding='utf-8') as f:
            dot = f.read()
        self.assertEqual(len(total_time_lines(dot)), 1)
        self.assertIn('label="Total time\\n14.7 s"', total_time_lines(dot)[0])
        # The gprof parser warns about this fixture's cycle entry; that is unrelated.
        self.assertNotIn('total time', err.getvalue())

    def test_flag_only_adds_one_line(self):
        plain, _ = self.run_main()
        with_node, _ = self.run_main('--show-total-time')
        plain_lines = plain.splitlines()
        node_lines = with_node.splitlines()
        self.assertEqual(len(node_lines), len(plain_lines) + 1)
        self.assertEqual([l for l in node_lines if '"[total time]"' not in l], plain_lines)

    def test_flag_survives_pruning(self):
        # Heavy pruning removes functions but the profile-wide total stays.
        dot, _ = self.run_main('--show-total-time', '-n', '50', '-e', '50')
        self.assertEqual(len(total_time_lines(dot)), 1)
        dot, _ = self.run_main('--show-total-time', '-z', 'memtrail:597:parse')
        self.assertEqual(len(total_time_lines(dot)), 1)

    def test_help_mentions_flag(self):
        out = io.StringIO()
        with self.assertRaises(SystemExit), redirect_stdout(out):
            gprof2dot.main(['--help'])
        self.assertIn('--show-total-time', out.getvalue())



if __name__ == '__main__':
    unittest.main()
