#!/bin/bash

set -o pipefail

usage()
{
	cat <<EOF
usage: ${0##*/} [-h] [-b PATTERN] [-c] [-n] [-u PATTERN]

optional arguments:
  -h              show this help message and exit
  -b PATTERN      Only execute black box tests matching PATTERN
  -c              Create HTML coverage report
  -n              Do not record coverage even if python3-coverage is found.
  -u PATTERN      Only execute unit tests matching PATTERN
EOF
}

run_unit_test()
{
	local ret LOGFILE=$(mktemp)

	echo -n "   ${1%%.py} ... "
	{
		echo "======================================================================"
		echo "Test: $1"
	} > "$LOGFILE"
	if $RUN_PYTHON3 -m unittest -v $1 >>"$LOGFILE" 2>&1 ; then
		echo "ok"
		ret=0
	else
		echo "FAIL (log follows...)"
		ret=1
		cat -n "$LOGFILE"
	fi

	cat "$LOGFILE" >> log.txt
	rm "$LOGFILE"
	return $ret
}

run_blackbox_test()
{
	local ret LOGFILE=$(mktemp)

	echo -n "   $1 ... "
	{
		echo "======================================================================"
		echo "Test: $1"
	} > "$LOGFILE"
	(
		set -o pipefail
		set -ex
		cd "$1"
		. run.sh 2>&1 | tee log.txt
	) >>"$LOGFILE" 2>&1

	ret=$?
	if [[ $ret -eq 240 ]] ; then
		echo "skipped"
		ret=0
	elif [[ $ret -ne 0 ]] ; then
		echo "FAIL (exit $ret, log follows...)"
		cat -n "$LOGFILE"
	else
		echo "ok"
	fi

	cat "$LOGFILE" >> log.txt
	rm "$LOGFILE"
	return $ret
}

# move to root directory
cd "${0%/*}/.."
. ./test/test-lib.sh

COVERAGE=
FAILED=0
RUN_TEST_DIRS=( )
GEN_HTML=0
unset RUN_UNITTEST_PAT
unset RUN_BLACKBOX_PAT

# check if python coverage is installed
if type -fp coverage3 >/dev/null; then
   COVERAGE=coverage3
elif type -fp python3-coverage >/dev/null; then
   COVERAGE=python3-coverage
fi

if [[ -n $COVERAGE ]] ; then
    # make sure coverage is installed in the current environment
    if python3 -c "import coverage" 2>/dev/null; then
        RUN_PYTHON3="$COVERAGE run --source $PWD/pym  --parallel-mode"
    else
        RUN_PYTHON3=python3
        COVERAGE=
        echo "coverage3 is installed but not in the current environment" >&2
    fi
else
	RUN_PYTHON3=python3
fi

# option processing
while getopts ":hb:cnu:" opt; do
	case $opt in
		h)
			usage
			exit 0
			;;
		b)
			RUN_BLACKBOX_PAT="$OPTARG"
			;;
		c)
			GEN_HTML=1
			;;
		n)
			RUN_PYTHON3=python3
			COVERAGE=
			;;
		u)
			RUN_UNITTEST_PAT="$OPTARG"
			;;
		\?)
			echo "Invalid option: -$OPTARG" >&2
			exit 1
			;;
	esac
done

# execute everything if nothing was specified
if [[ -z ${RUN_UNITTEST_PAT+isset} && -z ${RUN_BLACKBOX_PAT+isset} ]] ; then
	RUN_BLACKBOX_PAT='*'
	RUN_UNITTEST_PAT='*'
else
	: "${RUN_BLACKBOX_PAT=}"
	: "${RUN_UNITTEST_PAT=}"
fi

# go to tests directory
pushd test > /dev/null

# add marker to log.txt
{
	echo "######################################################################"
	echo -n "Started: "
	date
	echo "Options: $*"
} >> log.txt

# run unit tests
if [[ -n "$RUN_UNITTEST_PAT" ]] ; then
	echo "Run unit tests..."
	RUN_TEST_NAMES=( )
	for i in test_*.py ; do
		if [[ "${i%%.py}" == $RUN_UNITTEST_PAT ]] ; then
			RUN_TEST_NAMES+=( "$i" )
		fi
	done

	for i in "${RUN_TEST_NAMES[@]}" ; do
		if ! run_unit_test "$i" ; then
			: $((FAILED++))
		fi
	done
fi

# run blackbox tests
if [[ -n "$RUN_BLACKBOX_PAT" ]] ; then
	echo "Run black box tests..."
	RUN_TEST_NAMES=( )
	for i in * ; do
		if [[ -d $i && -e "$i/run.sh" && "$i" == $RUN_BLACKBOX_PAT ]] ; then
			RUN_TEST_DIRS+=( "test/$i" )
			RUN_TEST_NAMES+=( "$i" )
		fi
	done

	for i in "${RUN_TEST_NAMES[@]}" ; do
		if ! run_blackbox_test "$i" ; then
			: $((FAILED++))
		fi
	done
fi

popd > /dev/null

# collect coverage
if [[ -n $COVERAGE ]]; then
	$COVERAGE combine test "${RUN_TEST_DIRS[@]}"
	if [[ $GEN_HTML -eq 1 ]] ; then
		$COVERAGE html
	fi
fi

exit $FAILED
