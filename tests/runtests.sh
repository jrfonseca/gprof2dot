#!/bin/sh

PYTHON=python2.5

GPROF2DOT=../gprof2dot.py

for FORMAT in prof pstats
do
	for INPUT in *.$FORMAT
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
