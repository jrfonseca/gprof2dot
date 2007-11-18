#!/bin/bash

set -e

PYTHON=python2.5

TESTDIR=`dirname "$0"`
GPROF2DOT=$TESTDIR/../gprof2dot.py

if [ "$1" ]
then
	FORMATS=$@
else
	FORMATS="prof pstats oprofile"
fi

for FORMAT in $FORMATS
do
	for INPUT in $TESTDIR/*.$FORMAT
	do
		NAME=${INPUT%%.$FORMAT}
		OUTPUT=$NAME.dot
		echo $PYTHON $GPROF2DOT -f $FORMAT -o $OUTPUT $INPUT
		$PYTHON $GPROF2DOT -f $FORMAT -o $OUTPUT $INPUT || continue
		echo dot -Tpng -o $NAME.png $OUTPUT
		dot -Tpng -o $NAME.png $OUTPUT || continue
	done
done
