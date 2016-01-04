# About _gprof2dot_

This is a Python script to convert the output from python's profiles into a [dot graph](http://www.graphviz.org/doc/info/lang.html). It is forked from the original version of the library to address Yelp's specific needs for finer-grained control over display of python profiles.

It has the following features:

  * reads output from:
    * [python profilers](http://docs.python.org/2/library/profile.html#profile-stats)
  * prunes nodes and edges below a certain threshold;
  * uses an heuristic to propagate time inside mutually recursive functions;
  * uses color efficiently to draw attention to hot-spots;
  * works on any platform where Python and graphviz is available, i.e, virtually anywhere.

**If you want an interactive viewer for gprof2dot output graphs, check [xdot.py](https://github.com/jrfonseca/xdot.py).**

## Example

This is the result from the [example data](http://linuxgazette.net/100/misc/vinayak/overall-profile.txt) in the [Linux Gazette article](http://linuxgazette.net/100/vinayak.html) with the default settings:

<!-- pngquant --speed=1 --ordered  --quality 0-85 ... -->
![Sample](sample.png)

# Requirements

  * [Python](http://www.python.org/download/): known to work with version 2.7 and 3.3; it will most likely _not_ work with earlier releases.
  * [Graphviz](http://www.graphviz.org/Download.php): tested with version 2.26.3, but should work fine with other versions.

## Windows users

  * Download and install [Python for Windows](http://www.python.org/download/)
  * Download and install [Graphviz for Windows](http://www.graphviz.org/Download_windows.php)

## Debian/Ubuntu users

  * Run:

        apt-get install python graphviz


# Download

  * [PyPI](https://pypi.python.org/pypi/gprof2dot/)

        pip install gprof2dot

  * [Standalone script](https://raw.githubusercontent.com/jrfonseca/gprof2dot/master/gprof2dot.py)

  * [Git repository](https://github.com/jrfonseca/gprof2dot)


# Documentation

## Usage

    Usage:
            gprof2dot.py [options] [file] ...
    
    Options:
      -h, --help            show this help message and exit
      -o FILE, --output=FILE
                            output filename [stdout]
      -n PERCENTAGE, --node-thres=PERCENTAGE
                            eliminate nodes below this threshold [default: 0.5]
      -e PERCENTAGE, --edge-thres=PERCENTAGE
                            eliminate edges below this threshold [default: 0.1]
      --total=TOTALMETHOD   preferred method of calculating total time: callratios
                            or callstacks (currently affects only perf format)
                            [default: callratios]
      -c THEME, --colormap=THEME
                            color map: color, pink, gray, bw, or print [default:
                            color]
      -s, --strip           strip function parameters, template parameters, and
                            const modifiers from demangled C++ function names
      -w, --wrap            wrap function names
      --show-samples        show function samples
      -z ROOT, --root=ROOT  prune call graph to show only descendants of specified
                            root function
      -l LEAF, --leaf=LEAF  prune call graph to show only ancestors of specified
                            leaf function
      --skew=THEME_SKEW     skew the colorization curve.  Values < 1.0 give more
                            variety to lower percentages.  Values > 1.0 give less
                            variety to lower percentages

## Examples

### python profile

    python -m profile -o output.pstats path/to/your/script arg1 arg2
    gprof2dot.py -f pstats output.pstats | dot -Tpng -o output.png

### python cProfile (formerly known as lsprof)

    python -m cProfile -o output.pstats path/to/your/script arg1 arg2
    gprof2dot.py -f pstats output.pstats | dot -Tpng -o output.png

### python hotshot profiler

The hotshot profiler does not include a main function. Use the [hotshotmain.py](hotshotmain.py) script instead.

    hotshotmain.py -o output.pstats path/to/your/script arg1 arg2
    gprof2dot.py -f pstats output.pstats | dot -Tpng -o output.png


## Output

A node in the output graph represents a function and has the following layout:

    +------------------------------+
    |        function name         |
    |       total time % (ms)      |
    |       self time % (ms)       |
    |         total calls          |
    +------------------------------+

where:

  * _total time %_ is the percentage of the running time spent in this function and all its children;
  * _self time %_ is the percentage of the running time spent in this function alone;
  * (ms) are the actual milliseconds spent in the function
  * _total calls_ is the total number of times this function was called (including recursive calls).

An edge represents the calls between two functions and has the following layout:

               total time %
                  calls
    parent --------------------> children

Where:

  * _total time %_ is the percentage of the running time transfered from the children to this parent (if available);
  * _calls_ is the number of calls the parent function called the children.

Note that in recursive cycles, the _total time %_ in the node is the same for the whole functions in the cycle, and there is no _total time %_ figure in the edges inside the cycle, since such figure would make no sense.

The color of the nodes and edges varies according to the _total time %_ value. In the default _temperature-like_ color-map, functions where most time is spent (hot-spots) are marked as saturated red, and functions where little time is spent are marked as dark blue. Note that functions where negligible or no time is spent do not appear in the graph by default.

## Frequently Asked Questions

### How can I generate a complete call graph?

By default `gprof2dot.py` generates a _partial_ call graph, excluding nodes and edges with little or no impact in the total computation time. If you want the full call graph then set a zero threshold for nodes and edges via the `-n` / `--node-thres`  and `-e` / `--edge-thres` options, as:

    gprof2dot.py -n0 -e0

### The node labels are too wide. How can I narrow them?

The node labels can get very wide when profiling C++ code, due to inclusion of scope, function arguments, and template arguments in demangled C++ function names.

If you do not need function and template arguments information, then pass the `-s` / `--strip` option to strip them.

If you want to keep all that information, or if the labels are still too wide, then you can pass the `-w` / `--wrap`, to wrap the labels. Note that because `dot` does not wrap labels automatically the label margins will not be perfectly aligned.

### Why there is no output, or it is all in the same color?

Likely, the total execution time is too short, so there is not enough precision in the profile to determine where time is being spent.

You can still force displaying the whole graph by setting a zero threshold for nodes and edges via the `-n` / `--node-thres`  and `-e` / `--edge-thres` options, as:

    gprof2dot.py -n0 -e0

But to get meaningful results you will need to find a way to run the program for a longer time period (aggregate results from multiple runs).

### Why don't the percentages add up?

You likely have an execution time too short, causing the round-off errors to be large.

See question above for ways to increase execution time.
