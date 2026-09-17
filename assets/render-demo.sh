#!/usr/bin/env bash
# Rebuild assets/hypercharge-query.gif from assets/demo.tape.
#
# vhs records the terminal frames; ffmpeg and gifsicle encode the GIF. (vhs 0.12
# exits without writing a GIF on some setups, so the encode is done here.)
#
# Run from the root of a repo wired with `hypercharge onboard`, after
# `hypercharge label-communities --path .`. Needs vhs, ffmpeg and gifsicle.
set -euo pipefail

out="assets/hypercharge-query.gif"
# Relative and not yet created: vhs rejects absolute Output paths and writes no
# frames into a directory that already exists.
frames=".vhs-frames.$$"
rm -rf "$frames"
trap 'rm -rf "$frames" "$frames.tape"' EXIT

sed "s|^Output .*|Output $frames/|" assets/demo.tape > "$frames.tape"
vhs -q "$frames.tape"

# Overlay the cursor layer, add 28px of terminal padding and a 16px grey frame
# (keeps the dark terminal distinct on both light and dark GitHub pages).
ffmpeg -hide_banner -loglevel error -y \
  -framerate 20 -i "$frames/frame-text-%05d.png" \
  -framerate 20 -i "$frames/frame-cursor-%05d.png" \
  -filter_complex "[0][1]overlay,pad=iw+56:ih+56:28:28:color=0x1E1E2E,pad=iw+32:ih+32:16:16:color=0x6E7681,split[a][b];[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle" \
  "$out"
gifsicle -O3 --lossy=30 -b "$out"

echo "$out: $(du -h "$out" | cut -f1)"
