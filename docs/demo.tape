# Records docs/demo.gif, the animation at the top of the README.
# Run from the repository root with dbdelta and VHS (https://github.com/charmbracelet/vhs)
# installed:  vhs docs/demo.tape
Output docs/demo.gif
Require dbdelta

Set Shell "bash"
Set FontSize 15
Set Width 1280
Set Height 800
Set Padding 24
Set TypingSpeed 35ms
Set Theme "Catppuccin Mocha"
# Keep colors when output goes through head.
Env FORCE_COLOR "1"
Env COLUMNS "110"

Hide
Type "cd examples/shop && clear" Enter
Show

Type "dbdelta diff current.sql desired.sql | head -34"
Sleep 400ms Enter
Sleep 6s

Type "clear" Enter
Type "dbdelta plan current.sql desired.sql --detect-renames | sed -n 13,40p"
Sleep 400ms Enter
Sleep 6s

Type "clear" Enter
Type "dbdelta check current.sql desired.sql --detect-renames > /dev/null; echo exit code $?"
Sleep 400ms Enter
Sleep 4s
