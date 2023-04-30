#!/bin/sh

[ -z "$WORKSPACE" ] && exit 1
[ -z "$PROJECT_NAME" ] && exit 1
[ "$PWD" != "$WORKSPACE" ] && exit 1
exit 0
