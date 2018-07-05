#!/usr/bin/env bash

DIRNAME=$1
PORT_NUMBER=$2

# Make sure it not running
pid=`ps -ax | grep SimpleHTTPServer  | grep -v grep | awk '{print $1}'`

if [ $pid > 0 ]; then
    echo "SimpleHTTPServer already running on $pid... Bye"
else
    echo "Starting SimpleHTTPServer"
    cd $DIRNAME
    python -m SimpleHTTPServer $PORT_NUMBER
fi

exit


