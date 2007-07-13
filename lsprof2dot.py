#!/usr/bin/env python
"""Generate a dot graph from cProfile output."""

__author__ = "Jose Fonseca"

__version__ = "0.2"


import sys
import os.path
import re
import optparse

import cProfile
import inspect


class Struct:
	"""Masquerade a dictionary with a structure-like behavior."""

	def __init__(self, attrs = None):
		if attrs is None:
			attrs = {}
		self.__dict__['_attrs'] = attrs

	def __getattr__(self, name):
		try:
			return self._attrs[name]
		except KeyError:
			raise AttributeError(name)

	def __setattr__(self, name, value):
		self._attrs[name] = value

	def __str__(self):
		return str(self._attrs)

	def __repr__(self):
		return repr(self._attrs)


class Parser:

	def __init__(self, prof):
		self.entries = prof.getstats()
		self.functions = {}
		self.cycles = {}
		self.total = 0
		self.indexes = {}

	def label(self, code):
		if isinstance(code, str):
			return code
		else:
			module = inspect.getmodule(code)
			if module:
				modulename = module.__name__
			else:
				modulename = os.path.splitext(code.co_filename)[0]

			return "%s.%s @ %d" % (modulename, code.co_name, code.co_firstlineno)

	def parse(self):
		for entry in self.entries:
			self.parse_entry(entry)

	def index(self, name):
		try:
			return self.indexes[name]
		except KeyError:
			index = len(self.indexes)
			self.indexes[name] = index
			return index

	def parse_entry(self, entry):
		self.total = max(entry.totaltime, self.total)

		function = Struct()

		code = entry.code
		name = self.label(code)

		# recursive calls are counted in entry.calls
		if entry.calls:
			calls = entry.calls
		else:
			calls = []

		function.name = name
		function.index = self.index(name)
		function.self = entry.inlinetime
		function.descendants = entry.totaltime - entry.inlinetime
		function.called = entry.callcount - entry.reccallcount
		function.called_self = entry.reccallcount
		function.children = []
		function.cycle = None

		for subentry in calls:
			code = subentry.code
			callee = Struct()

			name = self.label(code)
			callee.index = self.index(name)
			callee.self = subentry.inlinetime
			callee.descendants = subentry.totaltime
			callee.called = subentry.callcount
			callee.cycle = None
			function.children.append(callee)

		self.functions[function.index] = function



class DotWriter:
	"""Writer for the DOT language.

	See also:
	- "The DOT Language" specification
	  http://www.graphviz.org/doc/info/lang.html
	"""

	def __init__(self, fp):
		self.fp = fp

	def begin_graph(self):
		self.write('digraph {\n')

	def end_graph(self):
		self.write('}\n')

	def attr(self, what, **attrs):
		self.write("\t")
		self.write(what)
		self.attr_list(attrs)
		self.write(";\n")

	def node(self, node, **attrs):
		self.write("\t")
		self.id(node)
		self.attr_list(attrs)
		self.write(";\n")

	def edge(self, src, dst, **attrs):
		self.write("\t")
		self.id(src)
		self.write(" -> ")
		self.id(dst)
		self.attr_list(attrs)
		self.write(";\n")

	def attr_list(self, attrs):
		if not attrs:
			return
		self.write(' [')
		first = True
		for name, value in attrs.iteritems():
			if first:
				first = False
			else:
				self.write(", ")
			self.id(name)
			self.write('=')
			self.id(value)
		self.write(']')

	def id(self, id):
		if isinstance(id, (int, float)):
			s = str(id)
		elif isinstance(id, str):
			if id.isalnum():
				s = id
			else:
				s = self.escape(id)
		else:
			raise TypeError
		self.write(s)

	def escape(self, s):
		s = s.replace('\\', r'\\')
		s = s.replace('\n', r'\n')
		s = s.replace('\t', r'\t')
		s = s.replace('"', r'\"')
		return '"' + s + '"'

	def write(self, s):
		self.fp.write(s)


class ColorMap:
	"""Color map."""

	def __init__(self, cmin, cmax, cpow = (1.0, 1.0, 1.0)):
		self.hmin, self.smin, self.lmin = cmin
		self.hmax, self.smax, self.lmax = cmax
		self.hpow, self.spow, self.lpow = cpow

	def color_from_percentage(self, p):
		"""Map a precentage value into a DOT color attribute value."""

		p /= 100.0

		h = self.hmin + p**self.hpow*(self.hmax - self.hmin)
		s = self.smin + p**self.spow*(self.smax - self.smin)
		l = self.lmin + p**self.lpow*(self.lmax - self.lmin)

		r, g, b = self.hsl_to_rgb(h, s, l)

		r = int(255.0*r + 0.5)
		g = int(255.0*g + 0.5)
		b = int(255.0*b + 0.5)

		return "#%02x%02x%02x" % (r, g, b)
		#return "%.03f+%.03f+%.03f" % (h, s, v)

	def hsl_to_rgb(self, h, s, l):
		"""Convert a color from HSL color-model to RGB.

		See also:
		- http://www.w3.org/TR/css3-color/#hsl-color
		"""
		if l <= 0.5:
			m2 = l*(s + 1.0)
		else:
			m2 = l + s - l*s
		m1 = l*2.0 - m2
		r = self._hue_to_rgb(m1, m2, h + 1.0/3.0)
		g = self._hue_to_rgb(m1, m2, h)
		b = self._hue_to_rgb(m1, m2, h - 1.0/3.0)
		return (r, g, b)

	def _hue_to_rgb(self, m1, m2, h):
		if h < 0.0:
			h += 1.0
		elif h > 1.0:
			h -= 1.0
		if h*6 < 1.0:
			return m1 + (m2 - m1)*h*6.0
		elif h*2 < 1.0:
			return m2
		elif h*3 < 2.0:
			return m1 + (m2 - m1)*(2.0/3.0 - h)*6.0
		else:
			return m1


class Main:
	"""Main program."""

	def main(self):
		"""Main program."""

		parser = optparse.OptionParser(
			usage="\n\t%prog [options] [file]",
			version="%%prog %s" % __version__)
		parser.add_option(
			'-o', '--output', metavar='FILE',
			type="string", dest="output",
			help="output filename [stdout]")
		parser.add_option(
			'-n', '--node-thres', metavar='PERCENTAGE',
			type="float", dest="node_thres", default=0.5,
			help="eliminate nodes below this threshold [default: %default]")
		parser.add_option(
			'-e', '--edge-thres', metavar='PERCENTAGE',
			type="float", dest="edge_thres", default=0.1,
			help="eliminate edges below this threshold [default: %default]")
		parser.add_option(
			'-c', '--colormap',
			type="choice", choices=('color', 'pink', 'gray'),
			dest="colormap", default="color",
			help="color map: color, pink or gray [default: %default]")
		parser.add_option(
			'-s', '--strip',
			action="store_true",
			dest="strip", default=False,
			help="strip function parameters, template parameters, and const modifiers from demangled C++ function names")
		parser.add_option(
			'-w', '--wrap',
			action="store_true",
			dest="wrap", default=False,
			help="wrap function names")
		(self.options, args) = parser.parse_args(sys.argv[1:])

		if len(args) < 1:
			parser.error('incorrect number of arguments')

		if self.options.output is None:
			self.options.output = '%s.dot' % os.path.basename(args[0])

		if self.options.colormap == "color":
			self.colormap = ColorMap(
				(2.0/3.0, 0.80, 0.25), # dark blue
				(0.0, 1.0, 0.5), # satured red
				(0.5, 1.0, 1.0), # slower hue gradation
			)
		elif self.options.colormap == "pink":
			self.colormap = ColorMap(
				(0.0, 1.0, 0.90), # pink
				(0.0, 1.0, 0.5), # satured red
				(1.0, 1.0, 1.0),
			)
		elif self.options.colormap == "gray":
			self.colormap = ColorMap(
				(0.0, 0.0, 0.925), # light gray
				(0.0, 0.0, 0.0), # black
				(1.0, 1.0, 1.0),
			)
		else:
			parser.error('invalid colormap \'%s\'' % self.options.colormap)

		sys.argv[:] = args
		prof = cProfile.Profile()
		try:
			try:
				prof = prof.run('execfile(%r)' % (sys.argv[0],))
			except SystemExit:
				pass
		finally:
			self.parser = Parser(prof)
			self.parser.parse()
			self.output = open(self.options.output, "wt")
			self.write_graph()


	def function_total(self, function):
		"""Calculate total time spent in function and descendants."""
		if function.cycle is not None:
			# function is part of a cycle so return total time spent in the cycle
			try:
				cycle = self.parser.cycles[function.cycle]
			except KeyError:
				# cycles discovered by gprof's static call graph analysis
				return 0.0
			else:
				return cycle.self + cycle.descendants
		else:
			assert function.self is not None
			assert function.descendants is not None
			return function.self + function.descendants

	_parenthesis_re = re.compile(r'\([^()]*\)')
	_angles_re = re.compile(r'<[^<>]*>')
	_const_re = re.compile(r'\s+const$')

	def strip_function_name(self, name):
		"""Remove extraneous information from C++ demangled function names."""

		# Strip function parameters from name by recursively removing paired parenthesis
		while True:
			name, n = self._parenthesis_re.subn('', name)
			if not n:
				break

		# Strip const qualifier
		name = self._const_re.sub('', name)

		# Strip template parameters from name by recursively removing paired angles
		while True:
			name, n = self._angles_re.subn('', name)
			if not n:
				break

		return name

	def wrap_function_name(self, name):
		"""Split the function name on multiple lines."""

		if len(name) > 32:
			ratio = 2.0/3.0
			height = max(int(len(name)/(1.0 - ratio) + 0.5), 1)
			width = max(len(name)/height, 32)
			# TODO: break lines in symbols
			name = textwrap.fill(name, width, break_long_words=False)

		# Take away spaces
		name = name.replace(", ", ",")
		name = name.replace("> >", ">>")
		name = name.replace("> >", ">>") # catch consecutive

		return name

	def compress_function_name(self, name):
		"""Compress function name according to the user preferences."""

		if self.options.strip:
			name = self.strip_function_name(name)

		if self.options.wrap:
			name = self.wrap_function_name(name)

		# TODO: merge functions with same resulting name

		return name

	fontname = "Helvetica"
	fontsize = "10"

	def write_graph(self):
		dot = DotWriter(self.output)
		dot.begin_graph()

		dot.attr('graph', fontname=self.fontname, fontsize=self.fontsize)
		dot.attr('node', fontname=self.fontname, fontsize=self.fontsize, shape="box", style="filled", fontcolor="white")
		dot.attr('edge', fontname=self.fontname, fontsize=self.fontsize)

		static_functions = {}
		for function in self.parser.functions.itervalues():
			name = function.name
			total_perc = self.function_total(function)/self.parser.total*100.0
			self_perc = function.self/self.parser.total*100.0

			if total_perc < self.options.node_thres:
				continue

			name = self.compress_function_name(name)
			label = "%s\n%.02f%% (%.02f%%)" % (name, total_perc, self_perc)

			# number of invocations
			if function.called is not None:
				total_called = function.called
				if function.called_self is not None:
					total_called += function.called_self
				label += "\n%i" % (total_called,)

			color = self.colormap.color_from_percentage(total_perc)
			dot.node(function.index, label=label, color=color)

			# NOTE: function.parents is not used
			for child in function.children:
				# only draw edge if destination node is not pruned
				try:
					child_ = self.parser.functions[child.index]
				except KeyError:
					# NOTE: functions that were never called but were discovered by gprof's
					# static call graph analysis dont have a call graph entry
					perc = 0.0
					static_functions[child.index] = child.name
				else:
					perc = self.function_total(child_)/self.parser.total*100.0
				if perc < self.options.node_thres:
					continue

				label = "%i"  % (child.called)

				if child.self is not None:
					assert child.descendants is not None
					perc = (child.self + child.descendants)/self.parser.total*100.0
					if perc < self.options.edge_thres:
						continue
					label = ("%.02f%%" % perc) + "\n" + label
				else:
					# recursive or intra-cycle call
					# no percentage value available but use parent's color
					perc = total_perc

				color = self.colormap.color_from_percentage(perc)
				dot.edge(function.index, child.index, label=label, color=color, fontcolor=color)

		# identical to the above, but for functions which do not have a call graph entry but appear in the
		# other entry callee list
		for index, name in static_functions.iteritems():
			total_perc = 0.0
			self_perc = 0.0

			if total_perc < self.options.node_thres:
				continue

			name = self.compress_function_name(name)
			label = "%s\n%.02f%% (%.02f%%)" % (name, total_perc, self_perc)

			# number of invocations
			total_called = 0
			label += "\n%i" % (total_called,)

			color = self.colormap.color_from_percentage(total_perc)
			dot.node(index, label=label, color=color)

		dot.end_graph()


if __name__ == '__main__':
	Main().main()
