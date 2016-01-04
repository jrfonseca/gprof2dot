#!/usr/bin/env python
#
# Copyright 2008-2014 Jose Fonseca
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

"""Generate a dot graph from the output of several profilers."""

__author__ = "Jose Fonseca et al"


import sys
import math
import os.path
import re
import textwrap
import optparse
import xml.parsers.expat
import collections
import locale
import json


# Python 2.x/3.x compatibility
if sys.version_info[0] >= 3:
    PYTHON_3 = True
    def compat_iteritems(x): return x.items()  # No iteritems() in Python 3
    def compat_itervalues(x): return x.values()  # No itervalues() in Python 3
    def compat_keys(x): return list(x.keys())  # keys() is a generator in Python 3
    basestring = str  # No class basestring in Python 3
    unichr = chr # No unichr in Python 3
    xrange = range # No xrange in Python 3
else:
    PYTHON_3 = False
    def compat_iteritems(x): return x.iteritems()
    def compat_itervalues(x): return x.itervalues()
    def compat_keys(x): return x.keys()


try:
    # Debugging helper module
    import debug
except ImportError:
    pass



########################################################################
# Model


MULTIPLICATION_SIGN = unichr(0xd7)


def times(x):
    return "%u%s" % (x, MULTIPLICATION_SIGN)

def percentage(p):
    return "%.02f%%" % (p*100.0,)

def add(a, b):
    return a + b

def fail(a, b):
    assert False


tol = 2 ** -23

def ratio(numerator, denominator):
    try:
        ratio = float(numerator)/float(denominator)
    except ZeroDivisionError:
        # 0/0 is undefined, but 1.0 yields more useful results
        return 1.0
    if ratio < 0.0:
        if ratio < -tol:
            sys.stderr.write('warning: negative ratio (%s/%s)\n' % (numerator, denominator))
        return 0.0
    if ratio > 1.0:
        if ratio > 1.0 + tol:
            sys.stderr.write('warning: ratio greater than one (%s/%s)\n' % (numerator, denominator))
        return 1.0
    return ratio


class UndefinedEvent(Exception):
    """Raised when attempting to get an event which is undefined."""

    def __init__(self, event):
        Exception.__init__(self)
        self.event = event

    def __str__(self):
        return 'unspecified event %s' % self.event.name


class Event(object):
    """Describe a kind of event, and its basic operations."""

    def __init__(self, name, null, aggregator, formatter=str):
        self.name = name
        self._null = null
        self._aggregator = aggregator
        self._formatter = formatter

    def __eq__(self, other):
        return self is other

    def __hash__(self):
        return id(self)

    def null(self):
        return self._null

    def aggregate(self, val1, val2):
        """Aggregate two event values."""
        assert val1 is not None
        assert val2 is not None
        return self._aggregator(val1, val2)

    def format(self, val):
        """Format an event value."""
        assert val is not None
        return self._formatter(val)


CALLS = Event("Calls", 0, add, times)

TIME = Event("Time", 0.0, add, lambda x: '(' + str(x) + ')')
TIME_RATIO = Event("Time ratio", 0.0, add, lambda x: '(' + percentage(x) + ')')
TOTAL_TIME = Event("Total time", 0.0, fail)
TOTAL_TIME_RATIO = Event("Total time ratio", 0.0, fail, percentage)


class Object(object):
    """Base class for all objects in profile which can store events."""

    def __init__(self, events=None):
        if events is None:
            self.events = {}
        else:
            self.events = events

    def __hash__(self):
        return id(self)

    def __eq__(self, other):
        return self is other

    def __contains__(self, event):
        return event in self.events

    def __getitem__(self, event):
        try:
            return self.events[event]
        except KeyError:
            raise UndefinedEvent(event)

    def __setitem__(self, event, value):
        if value is None:
            if event in self.events:
                del self.events[event]
        else:
            self.events[event] = value


class Call(Object):
    """A call between functions.

    There should be at most one call object for every pair of functions.
    """

    def __init__(self, callee_id):
        Object.__init__(self)
        self.callee_id = callee_id
        self.ratio = None
        self.weight = None


class Function(Object):
    """A function."""

    def __init__(self, id, name):
        Object.__init__(self)
        self.id = id
        self.name = name
        self.module = None
        self.process = None
        self.calls = {}
        self.called = None
        self.weight = None
        self.cycle = None
        self.filename = None

    def add_call(self, call):
        if call.callee_id in self.calls:
            sys.stderr.write('warning: overwriting call from function %s to %s\n' % (str(self.id), str(call.callee_id)))
        self.calls[call.callee_id] = call

    def get_call(self, callee_id):
        if not callee_id in self.calls:
            call = Call(callee_id)
            call[CALLS] = 0
            self.calls[callee_id] = call
        return self.calls[callee_id]

    _parenthesis_re = re.compile(r'\([^()]*\)')
    _angles_re = re.compile(r'<[^<>]*>')
    _const_re = re.compile(r'\s+const$')

    def stripped_name(self):
        """Remove extraneous information from C++ demangled function names."""

        name = self.name

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

    # TODO: write utility functions

    def __repr__(self):
        return self.name


class Cycle(Object):
    """A cycle made from recursive function calls."""

    def __init__(self):
        Object.__init__(self)
        self.functions = set()

    def add_function(self, function):
        assert function not in self.functions
        self.functions.add(function)
        if function.cycle is not None:
            for other in function.cycle.functions:
                if function not in self.functions:
                    self.add_function(other)
        function.cycle = self


class Profile(Object):
    """The whole profile."""

    def __init__(self):
        Object.__init__(self)
        self.functions = {}
        self.cycles = []

    def add_function(self, function):
        if function.id in self.functions:
            sys.stderr.write('warning: overwriting function %s (id %s)\n' % (function.name, str(function.id)))
        self.functions[function.id] = function

    def add_cycle(self, cycle):
        self.cycles.append(cycle)

    def validate(self):
        """Validate the edges."""

        for function in compat_itervalues(self.functions):
            for callee_id in compat_keys(function.calls):
                assert function.calls[callee_id].callee_id == callee_id
                if callee_id not in self.functions:
                    sys.stderr.write('warning: call to undefined function %s from function %s\n' % (str(callee_id), function.name))
                    del function.calls[callee_id]

    def find_cycles(self):
        """Find cycles using Tarjan's strongly connected components algorithm."""

        # Apply the Tarjan's algorithm successively until all functions are visited
        visited = set()
        for function in compat_itervalues(self.functions):
            if function not in visited:
                self._tarjan(function, 0, [], {}, {}, visited)
        cycles = []
        for function in compat_itervalues(self.functions):
            if function.cycle is not None and function.cycle not in cycles:
                cycles.append(function.cycle)
        self.cycles = cycles
        if 0:
            for cycle in cycles:
                sys.stderr.write("Cycle:\n")
                for member in cycle.functions:
                    sys.stderr.write("\tFunction %s\n" % member.name)

    def prune_root(self, root):
        visited = set()
        frontier = set([root])
        while len(frontier) > 0:
            node = frontier.pop()
            visited.add(node)
            f = self.functions[node]
            newNodes = f.calls.keys()
            frontier = frontier.union(set(newNodes) - visited)
        subtreeFunctions = {}
        for n in visited:
            subtreeFunctions[n] = self.functions[n]
        self.functions = subtreeFunctions

    def prune_leaf(self, leaf):
        edgesUp = collections.defaultdict(set)
        for f in self.functions.keys():
            for n in self.functions[f].calls.keys():
                edgesUp[n].add(f)
        # build the tree up
        visited = set()
        frontier = set([leaf])
        while len(frontier) > 0:
            node = frontier.pop()
            visited.add(node)
            frontier = frontier.union(edgesUp[node] - visited)
        downTree = set(self.functions.keys())
        upTree = visited
        path = downTree.intersection(upTree)
        pathFunctions = {}
        for n in path:
            f = self.functions[n]
            newCalls = {}
            for c in f.calls.keys():
                if c in path:
                    newCalls[c] = f.calls[c]
            f.calls = newCalls
            pathFunctions[n] = f
        self.functions = pathFunctions


    def getFunctionId(self, funcName):
        for f in self.functions:
            if self.functions[f].name == funcName:
                return f
        return False

    def _tarjan(self, function, order, stack, orders, lowlinks, visited):
        """Tarjan's strongly connected components algorithm.

        See also:
        - http://en.wikipedia.org/wiki/Tarjan's_strongly_connected_components_algorithm
        """

        visited.add(function)
        orders[function] = order
        lowlinks[function] = order
        order += 1
        pos = len(stack)
        stack.append(function)
        for call in compat_itervalues(function.calls):
            callee = self.functions[call.callee_id]
            # TODO: use a set to optimize lookup
            if callee not in orders:
                order = self._tarjan(callee, order, stack, orders, lowlinks, visited)
                lowlinks[function] = min(lowlinks[function], lowlinks[callee])
            elif callee in stack:
                lowlinks[function] = min(lowlinks[function], orders[callee])
        if lowlinks[function] == orders[function]:
            # Strongly connected component found
            members = stack[pos:]
            del stack[pos:]
            if len(members) > 1:
                cycle = Cycle()
                for member in members:
                    cycle.add_function(member)
        return order

    def call_ratios(self, event):
        # Aggregate for incoming calls
        cycle_totals = {}
        for cycle in self.cycles:
            cycle_totals[cycle] = 0.0
        function_totals = {}
        for function in compat_itervalues(self.functions):
            function_totals[function] = 0.0

        # Pass 1:  function_total gets the sum of call[event] for all
        #          incoming arrows.  Same for cycle_total for all arrows
        #          that are coming into the *cycle* but are not part of it.
        for function in compat_itervalues(self.functions):
            for call in compat_itervalues(function.calls):
                if call.callee_id != function.id:
                    callee = self.functions[call.callee_id]
                    if event in call.events:
                        function_totals[callee] += call[event]
                        if callee.cycle is not None and callee.cycle is not function.cycle:
                            cycle_totals[callee.cycle] += call[event]
                    else:
                        sys.stderr.write("call_ratios: No data for " + function.name + " call to " + callee.name + "\n")

        # Pass 2:  Compute the ratios.  Each call[event] is scaled by the
        #          function_total of the callee.  Calls into cycles use the
        #          cycle_total, but not calls within cycles.
        for function in compat_itervalues(self.functions):
            for call in compat_itervalues(function.calls):
                assert call.ratio is None
                if call.callee_id != function.id:
                    callee = self.functions[call.callee_id]
                    if event in call.events:
                        if callee.cycle is not None and callee.cycle is not function.cycle:
                            total = cycle_totals[callee.cycle]
                        else:
                            total = function_totals[callee]
                        call.ratio = ratio(call[event], total)
                    else:
                        # Warnings here would only repeat those issued above.
                        call.ratio = 0.0

    def integrate(self, outevent, inevent):
        """Propagate function time ratio along the function calls.

        Must be called after finding the cycles.

        See also:
        - http://citeseer.ist.psu.edu/graham82gprof.html
        """

        # Sanity checking
        assert outevent not in self
        for function in compat_itervalues(self.functions):
            assert outevent not in function
            assert inevent in function
            for call in compat_itervalues(function.calls):
                assert outevent not in call
                if call.callee_id != function.id:
                    assert call.ratio is not None

        # Aggregate the input for each cycle
        for cycle in self.cycles:
            total = inevent.null()
            for function in compat_itervalues(self.functions):
                total = inevent.aggregate(total, function[inevent])
            self[inevent] = total

        # Integrate along the edges
        total = inevent.null()
        for function in compat_itervalues(self.functions):
            total = inevent.aggregate(total, function[inevent])
            self._integrate_function(function, outevent, inevent)
        self[outevent] = total

    def _integrate_function(self, function, outevent, inevent):
        if function.cycle is not None:
            return self._integrate_cycle(function.cycle, outevent, inevent)
        else:
            if outevent not in function:
                total = function[inevent]
                for call in compat_itervalues(function.calls):
                    if call.callee_id != function.id:
                        total += self._integrate_call(call, outevent, inevent)
                function[outevent] = total
            return function[outevent]

    def _integrate_call(self, call, outevent, inevent):
        assert outevent not in call
        assert call.ratio is not None
        callee = self.functions[call.callee_id]
        subtotal = call.ratio *self._integrate_function(callee, outevent, inevent)
        call[outevent] = subtotal
        return subtotal

    def _integrate_cycle(self, cycle, outevent, inevent):
        if outevent not in cycle:

            # Compute the outevent for the whole cycle
            total = inevent.null()
            for member in cycle.functions:
                subtotal = member[inevent]
                for call in compat_itervalues(member.calls):
                    callee = self.functions[call.callee_id]
                    if callee.cycle is not cycle:
                        subtotal += self._integrate_call(call, outevent, inevent)
                total += subtotal
            cycle[outevent] = total

            # Compute the time propagated to callers of this cycle
            callees = {}
            for function in compat_itervalues(self.functions):
                if function.cycle is not cycle:
                    for call in compat_itervalues(function.calls):
                        callee = self.functions[call.callee_id]
                        if callee.cycle is cycle:
                            try:
                                callees[callee] += call.ratio
                            except KeyError:
                                callees[callee] = call.ratio

            for member in cycle.functions:
                member[outevent] = outevent.null()

            for callee, call_ratio in compat_iteritems(callees):
                ranks = {}
                call_ratios = {}
                partials = {}
                self._rank_cycle_function(cycle, callee, 0, ranks)
                self._call_ratios_cycle(cycle, callee, ranks, call_ratios, set())
                partial = self._integrate_cycle_function(cycle, callee, call_ratio, partials, ranks, call_ratios, outevent, inevent)
                assert partial == max(partials.values())
                assert abs(call_ratio*total - partial) <= 0.001*call_ratio*total

        return cycle[outevent]

    def _rank_cycle_function(self, cycle, function, rank, ranks):
        if function not in ranks or ranks[function] > rank:
            ranks[function] = rank
            for call in compat_itervalues(function.calls):
                if call.callee_id != function.id:
                    callee = self.functions[call.callee_id]
                    if callee.cycle is cycle:
                        self._rank_cycle_function(cycle, callee, rank + 1, ranks)

    def _call_ratios_cycle(self, cycle, function, ranks, call_ratios, visited):
        if function not in visited:
            visited.add(function)
            for call in compat_itervalues(function.calls):
                if call.callee_id != function.id:
                    callee = self.functions[call.callee_id]
                    if callee.cycle is cycle:
                        if ranks[callee] > ranks[function]:
                            call_ratios[callee] = call_ratios.get(callee, 0.0) + call.ratio
                            self._call_ratios_cycle(cycle, callee, ranks, call_ratios, visited)

    def _integrate_cycle_function(self, cycle, function, partial_ratio, partials, ranks, call_ratios, outevent, inevent):
        if function not in partials:
            partial = partial_ratio*function[inevent]
            for call in compat_itervalues(function.calls):
                if call.callee_id != function.id:
                    callee = self.functions[call.callee_id]
                    if callee.cycle is not cycle:
                        assert outevent in call
                        partial += partial_ratio*call[outevent]
                    else:
                        if ranks[callee] > ranks[function]:
                            callee_partial = self._integrate_cycle_function(cycle, callee, partial_ratio, partials, ranks, call_ratios, outevent, inevent)
                            call_ratio = ratio(call.ratio, call_ratios[callee])
                            call_partial = call_ratio*callee_partial
                            try:
                                call[outevent] += call_partial
                            except UndefinedEvent:
                                call[outevent] = call_partial
                            partial += call_partial
            partials[function] = partial
            try:
                function[outevent] += partial
            except UndefinedEvent:
                function[outevent] = partial
        return partials[function]

    def aggregate(self, event):
        """Aggregate an event for the whole profile."""

        total = event.null()
        for function in compat_itervalues(self.functions):
            try:
                total = event.aggregate(total, function[event])
            except UndefinedEvent:
                return
        self[event] = total

    def ratio(self, outevent, inevent):
        assert outevent not in self
        assert inevent in self
        for function in compat_itervalues(self.functions):
            assert outevent not in function
            assert inevent in function
            function[outevent] = ratio(function[inevent], self[inevent])
            for call in compat_itervalues(function.calls):
                assert outevent not in call
                if inevent in call:
                    call[outevent] = ratio(call[inevent], self[inevent])
        self[outevent] = 1.0

    def prune(self, node_thres, edge_thres):
        """Prune the profile"""

        # compute the prune ratios
        for function in compat_itervalues(self.functions):
            try:
                function.weight = function[TOTAL_TIME_RATIO]
            except UndefinedEvent:
                pass

            for call in compat_itervalues(function.calls):
                callee = self.functions[call.callee_id]

                if TOTAL_TIME_RATIO in call:
                    # handle exact cases first
                    call.weight = call[TOTAL_TIME_RATIO]
                else:
                    try:
                        # make a safe estimate
                        call.weight = min(function[TOTAL_TIME_RATIO], callee[TOTAL_TIME_RATIO])
                    except UndefinedEvent:
                        pass

        # prune the nodes
        for function_id in compat_keys(self.functions):
            function = self.functions[function_id]
            if function.weight is not None:
                if function.weight < node_thres:
                    del self.functions[function_id]

        # prune the egdes
        for function in compat_itervalues(self.functions):
            for callee_id in compat_keys(function.calls):
                call = function.calls[callee_id]
                if callee_id not in self.functions or call.weight is not None and call.weight < edge_thres:
                    del function.calls[callee_id]

    def dump(self):
        for function in compat_itervalues(self.functions):
            sys.stderr.write('Function %s:\n' % (function.name,))
            self._dump_events(function.events)
            for call in compat_itervalues(function.calls):
                callee = self.functions[call.callee_id]
                sys.stderr.write('  Call %s:\n' % (callee.name,))
                self._dump_events(call.events)
        for cycle in self.cycles:
            sys.stderr.write('Cycle:\n')
            self._dump_events(cycle.events)
            for function in cycle.functions:
                sys.stderr.write('  Function %s\n' % (function.name,))

    def _dump_events(self, events):
        for event, value in compat_iteritems(events):
            sys.stderr.write('    %s: %s\n' % (event.name, event.format(value)))



########################################################################
# Parsers


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


class ParseError(Exception):
    """Raised when parsing to signal mismatches."""

    def __init__(self, msg, line):
        Exception.__init__(self)
        self.msg = msg
        # TODO: store more source line information
        self.line = line

    def __str__(self):
        return '%s: %r' % (self.msg, self.line)


class Parser:
    """Parser interface."""

    stdinInput = True
    multipleInput = False

    def __init__(self):
        pass

    def parse(self):
        raise NotImplementedError


class PstatsParser:
    """Parser python profiling statistics saved with te pstats module."""

    stdinInput = False
    multipleInput = True

    def __init__(self, *filename):
        import pstats
        try:
            self.stats = pstats.Stats(*filename)
        except ValueError:
            if PYTHON_3:
                sys.stderr.write('error: failed to load %s\n' % ', '.join(filename))
                sys.exit(1)
            import hotshot.stats
            self.stats = hotshot.stats.load(filename[0])
        self.profile = Profile()
        self.function_ids = {}

    def get_function_name(self, key):
        filename, line, name = key
        module = os.path.splitext(filename)[0]
        module = os.path.basename(module)
        return "%s:%d:%s" % (module, line, name)

    def get_function(self, key):
        try:
            id = self.function_ids[key]
        except KeyError:
            id = len(self.function_ids)
            name = self.get_function_name(key)
            function = Function(id, name)
            function.filename = key[0]
            self.profile.functions[id] = function
            self.function_ids[key] = id
        else:
            function = self.profile.functions[id]
        return function

    def parse(self):
        self.profile[TIME] = 0.0
        self.profile[TOTAL_TIME] = self.stats.total_tt
        for fn, (cc, nc, tt, ct, callers) in compat_iteritems(self.stats.stats):
            callee = self.get_function(fn)
            callee.called = nc
            callee[TOTAL_TIME] = ct
            callee[TIME] = tt
            self.profile[TIME] += tt
            self.profile[TOTAL_TIME] = max(self.profile[TOTAL_TIME], ct)
            for fn, value in compat_iteritems(callers):
                caller = self.get_function(fn)
                call = Call(callee.id)
                if isinstance(value, tuple):
                    for i in xrange(0, len(value), 4):
                        nc, cc, tt, ct = value[i:i+4]
                        if CALLS in call:
                            call[CALLS] += cc
                        else:
                            call[CALLS] = cc

                        if TOTAL_TIME in call:
                            call[TOTAL_TIME] += ct
                        else:
                            call[TOTAL_TIME] = ct

                else:
                    call[CALLS] = value
                    call[TOTAL_TIME] = ratio(value, nc)*ct

                caller.add_call(call)

        # Compute derived events
        self.profile.validate()
        self.profile.ratio(TIME_RATIO, TIME)
        self.profile.ratio(TOTAL_TIME_RATIO, TOTAL_TIME)

        return self.profile


########################################################################
# Output


class Theme:

    def __init__(self,
            bgcolor = (0.0, 0.0, 1.0),
            mincolor = (0.0, 0.0, 0.0),
            maxcolor = (0.0, 0.0, 1.0),
            fontname = "Arial",
            fontcolor = "white",
            nodestyle = "filled",
            minfontsize = 10.0,
            maxfontsize = 10.0,
            minpenwidth = 0.5,
            maxpenwidth = 4.0,
            gamma = 2.2,
            skew = 1.0):
        self.bgcolor = bgcolor
        self.mincolor = mincolor
        self.maxcolor = maxcolor
        self.fontname = fontname
        self.fontcolor = fontcolor
        self.nodestyle = nodestyle
        self.minfontsize = minfontsize
        self.maxfontsize = maxfontsize
        self.minpenwidth = minpenwidth
        self.maxpenwidth = maxpenwidth
        self.gamma = gamma
        self.skew = skew

    def graph_bgcolor(self):
        return self.hsl_to_rgb(*self.bgcolor)

    def graph_fontname(self):
        return self.fontname

    def graph_fontcolor(self):
        return self.fontcolor

    def graph_fontsize(self):
        return self.minfontsize

    def node_bgcolor(self, weight):
        return self.color(weight)

    def node_fgcolor(self, weight):
        if self.nodestyle == "filled":
            return self.graph_bgcolor()
        else:
            return self.color(weight)

    def node_fontsize(self, weight):
        return self.fontsize(weight)

    def node_style(self):
        return self.nodestyle

    def edge_color(self, weight):
        return self.color(weight)

    def edge_fontsize(self, weight):
        return self.fontsize(weight)

    def edge_penwidth(self, weight):
        return max(weight*self.maxpenwidth, self.minpenwidth)

    def edge_arrowsize(self, weight):
        return 0.5 * math.sqrt(self.edge_penwidth(weight))

    def fontsize(self, weight):
        return max(weight**2 * self.maxfontsize, self.minfontsize)

    def color(self, weight):
        weight = min(max(weight, 0.0), 1.0)

        hmin, smin, lmin = self.mincolor
        hmax, smax, lmax = self.maxcolor

        if self.skew < 0:
            raise ValueError("Skew must be greater than 0")
        elif self.skew == 1.0:
            h = hmin + weight*(hmax - hmin)
            s = smin + weight*(smax - smin)
            l = lmin + weight*(lmax - lmin)
        else:
            base = self.skew
            h = hmin + ((hmax-hmin)*(-1.0 + (base ** weight)) / (base - 1.0))
            s = smin + ((smax-smin)*(-1.0 + (base ** weight)) / (base - 1.0))
            l = lmin + ((lmax-lmin)*(-1.0 + (base ** weight)) / (base - 1.0))

        return self.hsl_to_rgb(h, s, l)

    def hsl_to_rgb(self, h, s, l):
        """Convert a color from HSL color-model to RGB.

        See also:
        - http://www.w3.org/TR/css3-color/#hsl-color
        """

        h = h % 1.0
        s = min(max(s, 0.0), 1.0)
        l = min(max(l, 0.0), 1.0)

        if l <= 0.5:
            m2 = l*(s + 1.0)
        else:
            m2 = l + s - l*s
        m1 = l*2.0 - m2
        r = self._hue_to_rgb(m1, m2, h + 1.0/3.0)
        g = self._hue_to_rgb(m1, m2, h)
        b = self._hue_to_rgb(m1, m2, h - 1.0/3.0)

        # Apply gamma correction
        r **= self.gamma
        g **= self.gamma
        b **= self.gamma

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


TEMPERATURE_COLORMAP = Theme(
    mincolor = (2.0/3.0, 0.80, 0.25), # dark blue
    maxcolor = (0.0, 1.0, 0.5), # satured red
    gamma = 1.0
)

PINK_COLORMAP = Theme(
    mincolor = (0.0, 1.0, 0.90), # pink
    maxcolor = (0.0, 1.0, 0.5), # satured red
)

GRAY_COLORMAP = Theme(
    mincolor = (0.0, 0.0, 0.85), # light gray
    maxcolor = (0.0, 0.0, 0.0), # black
)

BW_COLORMAP = Theme(
    minfontsize = 8.0,
    maxfontsize = 24.0,
    mincolor = (0.0, 0.0, 0.0), # black
    maxcolor = (0.0, 0.0, 0.0), # black
    minpenwidth = 0.1,
    maxpenwidth = 8.0,
)

PRINT_COLORMAP = Theme(
    minfontsize = 18.0,
    maxfontsize = 30.0,
    fontcolor = "black",
    nodestyle = "solid",
    mincolor = (0.0, 0.0, 0.0), # black
    maxcolor = (0.0, 0.0, 0.0), # black
    minpenwidth = 0.1,
    maxpenwidth = 8.0,
)


themes = {
    "color": TEMPERATURE_COLORMAP,
    "pink": PINK_COLORMAP,
    "gray": GRAY_COLORMAP,
    "bw": BW_COLORMAP,
    "print": PRINT_COLORMAP,
}


def sorted_iteritems(d):
    # Used mostly for result reproducibility (while testing.)
    keys = compat_keys(d)
    keys.sort()
    for key in keys:
        value = d[key]
        yield key, value


class DotWriter:
    """Writer for the DOT language.

    See also:
    - "The DOT Language" specification
      http://www.graphviz.org/doc/info/lang.html
    """

    strip = False
    wrap = False

    def __init__(self, fp):
        self.fp = fp

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

    def _name_label(self, function):
        if self.strip:
            function_name = function.stripped_name()
        else:
            function_name = function.name
        if self.wrap:
            function_name = self.wrap_function_name(function_name)
        return function_name

    def _total_time_ratio_label(self, function, total_time):
        ratio = function[TOTAL_TIME_RATIO]
        return "{ratio:.2f}% ({time:.0f}ms)".format(
            ratio=ratio,
            time=ratio*total_time*1000,
        )

    def _time_ratio_label(self, function, total_time):
        ratio = function[TIME_RATIO]
        return "{ratio:.2f}% ({time:.1f}ms)".format(
            ratio=ratio,
            time=ratio*total_time*1000,
        )

    def _called_label(self, function):
        return u"{called}{sign}".format(called=function.called, sign=MULTIPLICATION_SIGN)

    def graph(self, profile, theme):
        self.begin_graph()

        fontname = theme.graph_fontname()
        fontcolor = theme.graph_fontcolor()
        nodestyle = theme.node_style()

        self.attr('graph', fontname=fontname, ranksep=0.25, nodesep=0.125)
        self.attr('node', fontname=fontname, shape="box", style=nodestyle, fontcolor=fontcolor, width=0, height=0)
        self.attr('edge', fontname=fontname)

        total_time = profile.events[TIME]

        for _, function in sorted_iteritems(profile.functions):
            labels = []

            labels.append(self._name_label(function))
            labels.append(self._total_time_ratio_label(function, total_time))
            labels.append(self._time_ratio_label(function, total_time))
            labels.append(self._called_label(function))

            if function.weight is not None:
                weight = function.weight
            else:
                weight = 0.0

            label = '\n'.join(labels)
            self.node(function.id,
                label = label,
                color = self.color(theme.node_bgcolor(weight)),
                fontcolor = self.color(theme.node_fgcolor(weight)),
                fontsize = "%.2f" % theme.node_fontsize(weight),
                tooltip = function.filename,
            )

            for _, call in sorted_iteritems(function.calls):
                callee = profile.functions[call.callee_id]

                labels = []
                for event in [TOTAL_TIME_RATIO, CALLS]:
                    if event in call.events:
                        label = event.format(call[event])
                        labels.append(label)

                if call.weight is not None:
                    weight = call.weight
                elif callee.weight is not None:
                    weight = callee.weight
                else:
                    weight = 0.0

                label = '\n'.join(labels)

                self.edge(function.id, call.callee_id,
                    label = label,
                    color = self.color(theme.edge_color(weight)),
                    fontcolor = self.color(theme.edge_color(weight)),
                    fontsize = "%.2f" % theme.edge_fontsize(weight),
                    penwidth = "%.2f" % theme.edge_penwidth(weight),
                    labeldistance = "%.2f" % theme.edge_penwidth(weight),
                    arrowsize = "%.2f" % theme.edge_arrowsize(weight),
                )

        self.end_graph()

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
        for name, value in sorted_iteritems(attrs):
            if value is None:
                continue
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
        elif isinstance(id, basestring):
            if id.isalnum() and not id.startswith('0x'):
                s = id
            else:
                s = self.escape(id)
        else:
            raise TypeError
        self.write(s)

    def color(self, rgb):
        r, g, b = rgb

        def float2int(f):
            if f <= 0.0:
                return 0
            if f >= 1.0:
                return 255
            return int(255.0*f + 0.5)

        return "#" + "".join(["%02x" % float2int(c) for c in (r, g, b)])

    def escape(self, s):
        if not PYTHON_3:
            s = s.encode('utf-8')
        s = s.replace('\\', r'\\')
        s = s.replace('\n', r'\n')
        s = s.replace('\t', r'\t')
        s = s.replace('"', r'\"')
        return '"' + s + '"'

    def write(self, s):
        self.fp.write(s)


########################################################################
# Main program


def naturalJoin(values):
    if len(values) >= 2:
        return ', '.join(values[:-1]) + ' or ' + values[-1]

    else:
        return ''.join(values)


def parse_options():
    optparser = optparse.OptionParser(
        usage="\n\t%prog [options] [file] ...")
    optparser.add_option(
        '-o', '--output', metavar='FILE',
        type="string", dest="output",
        help="output filename [stdout]")
    optparser.add_option(
        '-n', '--node-thres', metavar='PERCENTAGE',
        type="float", dest="node_thres", default=0.5,
        help="eliminate nodes below this threshold [default: %default]")
    optparser.add_option(
        '-e', '--edge-thres', metavar='PERCENTAGE',
        type="float", dest="edge_thres", default=0.1,
        help="eliminate edges below this threshold [default: %default]")
    optparser.add_option(
        '-c', '--colormap',
        type="choice", choices=('color', 'pink', 'gray', 'bw', 'print'),
        dest="theme", default="color",
        help="color map: color, pink, gray, bw, or print [default: %default]")
    optparser.add_option(
        '-s', '--strip',
        action="store_true",
        dest="strip", default=False,
        help="strip function parameters, template parameters, and const modifiers from demangled C++ function names")
    optparser.add_option(
        '-w', '--wrap',
        action="store_true",
        dest="wrap", default=False,
        help="wrap function names")
    # add option to create subtree or show paths
    optparser.add_option(
        '-z', '--root',
        type="string",
        dest="root", default="",
        help="prune call graph to show only descendants of specified root function")
    optparser.add_option(
        '-l', '--leaf',
        type="string",
        dest="leaf", default="",
        help="prune call graph to show only ancestors of specified leaf function")
    # add a new option to control skew of the colorization curve
    optparser.add_option(
        '--skew',
        type="float", dest="theme_skew", default=1.0,
        help="skew the colorization curve.  Values < 1.0 give more variety to lower percentages.  Values > 1.0 give less variety to lower percentages")
    (options, args) = optparser.parse_args(sys.argv[1:])
    return options, args


def main():
    """Main program."""
    options, args = parse_options()

    try:
        theme = themes[options.theme]
    except KeyError:
        optparser.error('invalid colormap \'%s\'' % options.theme)

    # set skew on the theme now that it has been picked.
    if options.theme_skew:
        theme.skew = options.theme_skew

    if not args:
        optparser.error('at least a file must be specified for pstats format')
    parser = PstatsParser(*args)

    profile = parser.parse()

    if options.output is None:
        output = sys.stdout
    else:
        if PYTHON_3:
            output = open(options.output, 'wt', encoding='UTF-8')
        else:
            output = open(options.output, 'wt')

    dot = DotWriter(output)
    dot.strip = options.strip
    dot.wrap = options.wrap

    profile = profile
    profile.prune(options.node_thres/100.0, options.edge_thres/100.0)

    if options.root:
        rootId = profile.getFunctionId(options.root)
        if not rootId:
            sys.stderr.write('root node ' + options.root + ' not found (might already be pruned : try -e0 -n0 flags)\n')
            sys.exit(1)
        profile.prune_root(rootId)
    if options.leaf:
        leafId = profile.getFunctionId(options.leaf)
        if not leafId:
            sys.stderr.write('leaf node ' + options.leaf + ' not found (maybe already pruned : try -e0 -n0 flags)\n')
            sys.exit(1)
        profile.prune_leaf(leafId)

    dot.graph(profile, theme)


if __name__ == '__main__':
    main()
