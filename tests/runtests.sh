#!/bin/bash

PYTHON=python

TESTDIR=`dirname "$0"`
GPROF2DOT=$TESTDIR/../gprof2dot.py

SNAPSHOT=
if [ "$1" == "-s" ]
then
	SNAPSHOT=y
	shift
fi

if [ "$1" ]
then
	FORMATS=$@
else
	FORMATS="prof pstats oprofile shark"
fi

for FORMAT in $FORMATS
do
	for PROFILE in $TESTDIR/*.$FORMAT
	do
		NAME=${PROFILE%%.$FORMAT}
		echo $PYTHON $GPROF2DOT -f $FORMAT -o $NAME.dot $PROFILE
		$PYTHON $GPROF2DOT -f $FORMAT -o $NAME.dot $PROFILE || continue
		echo dot -Tpng -o $NAME.png $NAME.dot
		dot -Tpng -o $NAME.png $NAME.dot || continue

		if [ "$SNAPSHOT" ]
		then
			cp -f $NAME.dot $NAME.orig.dot
			cp -f $NAME.png $NAME.orig.png
		else
			diff $NAME.orig.dot $NAME.dot
		fi
	done
done
