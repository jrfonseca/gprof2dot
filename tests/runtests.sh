#!/bin/sh

PYTHON=python2.5

TESTDIR=`dirname "$0"`
GPROF2DOT=$TESTDIR/../gprof2dot.py

for FORMAT in prof pstats
do
	for INPUT in $TESTDIR/*.$FORMAT
	do
		NAME=${INPUT%%.$FORMAT}
		OUTPUT=$NAME.dot
		echo $INPUT
		if ! $PYTHON $GPROF2DOT -f $FORMAT -o $OUTPUT $INPUT
		then
			echo FAILED
		else
			# TODO: regression testing
			dot -Tpng -o $NAME.png $OUTPUT
			echo OK
		fi
	done
done
