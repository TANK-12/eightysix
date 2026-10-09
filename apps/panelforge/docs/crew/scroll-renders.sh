#!/bin/sh
# Emerson (17:55): "make it do lots of renders" -- whole-chapter scroll-reader films
cd /home/ejb/Forge/apps/panelforge || exit 1
for spec in "0001 scroll-16x9 16:9" "0001 scroll-9x16 9:16" "0002 scroll-16x9 16:9" "0003 scroll-16x9 16:9"; do
  set -- $spec
  echo "== $1 $2 $(date +%H:%M:%S)"
  .venv/bin/python tools/scroll_render.py bad-born-blood $1 $2 0 $3 2>&1 | grep -v Warning | tail -2
done
echo "== scroll renders done $(date +%H:%M:%S)"
