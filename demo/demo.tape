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
Set TypingSpeed 35ms

Sleep 500ms
Type "angrist fix --file demo/payment_processor.py --target PaymentProcessor.settle_batch --instruction 'Fix fee deduction precedence and update transaction status' --test-cmd 'pytest demo/test_payment_processor.py'"
Sleep 500ms
Enter

Sleep 5s

Type "angrist benchmark"
Sleep 500ms
Enter

Sleep 6s
