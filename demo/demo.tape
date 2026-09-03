# VHS documentation tape for Angrist demo
# Run via: demo/record_demo.ps1
# Output: demo/demo.gif

Output demo/demo.gif

Env ANGRIST_LLM_BASE_URL "http://127.0.0.1:8765/v1"
Env ANGRIST_LLM_API_KEY "mock-key"
Env ANGRIST_LLM_MODEL "gpt-oss-mock"

Set FontSize 14
Set Width 1050
Set Height 580
Set Padding 24
Set Theme "Catppuccin Mocha"
Set WindowBar Colorful
Set TypingSpeed 30ms

Sleep 500ms

Type "angrist fix --file demo/payment_processor.py --target PaymentProcessor.settle_batch"
Sleep 300ms
Type " --instruction 'Fix fee deduction precedence'"
Sleep 300ms
Type " --test-cmd 'pytest demo/test_payment_processor.py'"
Sleep 500ms
Enter

Sleep 20s

Type "angrist benchmark"
Sleep 500ms
Enter

Sleep 12s
