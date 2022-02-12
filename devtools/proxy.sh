#!/bin/sh

set -o nounset   # Don't allow unset variables
set -o errexit   # Exit if any command fails

port="${1:-1337}"
remote="${2:-${USER}@localhost}"

ssh -v -nNt -D "$port" "$remote"
