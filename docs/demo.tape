# Re-record the README demo: `vhs docs/demo.tape` from the repo root, with pagecite installed in .venv.
# It runs `pagecite demo`: a fictional report and a sample summary (no API call); the checks are real.
Output docs/demo.gif

Set Shell zsh
Set FontSize 13
Set Width 1180
Set Height 680
Set Padding 14
Set Framerate 15
Set TypingSpeed 55ms
Set Theme { "background": "#000000", "foreground": "#e0e0e0" }

Hide
Type "export PATH=$PWD/.venv/bin:$PATH PS1='$ ' && clear"
Enter
Sleep 1s
Show

Type "pagecite demo"
Sleep 600ms
Enter
Sleep 9s
