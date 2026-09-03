# VHS documentation tape for Angrist demo
# Run: vhs demo/demo.tape
# Output: demo/demo.gif

Output demo/demo.gif

Set Shell "bash"
Set FontSize 15
Set Width 1050
Set Height 580
Set Padding 24
Set Theme "Catppuccin Mocha"
Set WindowBar Colorful
Set TypingSpeed 40ms

Sleep 500ms
Type "angrist fix --file demo/calculator.py --target calculate_discount --instruction 'Fix zero division bug'"
Sleep 500ms
Enter

Sleep 4s

Type "angrist benchmark --filter requests"
Sleep 500ms
Enter

Sleep 5s
