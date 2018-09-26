#!/usr/bin/env bash

DIRNAME=$1
PORT_NUMBER=$2

# Get the python version
PyVERSION=`python -c 'import sys; print(sys.version_info[0])'`

if [[ $PyVERSION == 3 ]]; then
    httpserver=http.server
elif [[ $PyVERSION == 2 ]]; then
    httpserver=SimpleHTTPServer
else
    echo "ERROR: Cannot identify python version"
    exit
fi

echo "Running Python$PyVERSION -- $httpserver"

# Make sure it not running
pid=`ps -ax | grep $httpserver | grep -v grep | awk '{print $1}'`

if [[ $pid > 0 ]]; then
    echo "$httpserver already running on $pid... Bye"
else
    echo "Starting $httpserver"
    cd $DIRNAME
    python -m $httpserver $PORT_NUMBER
fi

exit
