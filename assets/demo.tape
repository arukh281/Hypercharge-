# Hero GIF for the README: the agent asks the code map before editing.
#
# Regenerate with `bash assets/render-demo.sh` (it records this tape and encodes the GIF).
# Run it from the root of a repo wired with `hypercharge onboard` (this repo works),
# after `hypercharge label-communities --path .` so the module map has names.
#
# The output is whatever `hypercharge query` prints on the day; nothing is faked.

Output assets/hypercharge-query.gif

Require hypercharge

Set Shell "bash"
Set FontSize 22
Set Width 1100
Set Height 720
Set Theme "Catppuccin Mocha"
Set TypingSpeed 40ms
Set Framerate 20

Hide
Type "export PS1='$ ' && clear"
Enter
Show

Sleep 600ms
Type "# Before editing, the agent asks the code map where things live"
Sleep 900ms
Enter
Type 'hypercharge query "where is the memory index searched"'
Sleep 700ms
Enter
Sleep 7s
