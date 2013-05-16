#!/bin/bash

PYTHON=${PYTHON:-python}

TESTDIR=`dirname "$0"`
GPROF2DOT=$TESTDIR/../gprof2dot.py

FORCE=
if [ "$1" == "-f" ]
then
       FORCE=y
       shift
fi

if [ "$1" ]
then
	FORMATS=$@
else
	FORMATS="
		axe
		callgrind
		hprof
		oprofile
		perf
		prof
		pstats
		sleepy
		sysprof
	"
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

		if [ ! -f $NAME.orig.dot -o "$FORCE" ]
		then
			cp -f $NAME.dot $NAME.orig.dot
			cp -f $NAME.png $NAME.orig.png
		else
			diff $NAME.orig.dot $NAME.dot
		fi
	done
done
