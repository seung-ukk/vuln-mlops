#!/bin/sh
set -eu
zero=0000000000000000000000000000000000000000
while read -r old new ref; do
  [ "$ref" = "refs/heads/lab-runtime" ] || { echo "only lab-runtime is writable" >&2; exit 1; }
  if [ "$old" = "$zero" ]; then
    files="$(git diff-tree --root --no-commit-id --name-only -r "$new")"
  else
    files="$(git diff --name-only "$old" "$new")"
  fi
  for file in $files; do
    case "$file" in runtime-builder/*) ;; *) echo "path denied: $file" >&2; exit 1 ;; esac
  done
done
