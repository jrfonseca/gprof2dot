#!/bin/sh

PYTHON=python2.5

PROF2DOT=../prof2dot.py

for FORMAT in prof pstats
do
	for INPUT in *.$FORMAT
	do
		NAME=${INPUT%%.$FORMAT}
		OUTPUT=$NAME.dot
		echo $INPUT
		if ! $PYTHON $PROF2DOT -f $FORMAT -o $OUTPUT $INPUT
		then
			echo FAILED
		else
			# TODO: regression testing
			dot -Tpng -o $NAME.png $OUTPUT
			echo OK
		fi
	done
done
