# VHS tape configuration for angrist
# Output: demo.gif
Output demo.gif

Set FontSize 15
Set Width 1200
Set Height 720
Set Padding 20
Set Theme "Catppuccin Mocha"
Set Shell "powershell.exe"
Set TypingSpeed 35ms

# Prepare environment (clear and start mock server in background)
Hide
Type "Start-Process python -ArgumentList 'demo/mock_server.py', '8089' -WindowStyle Hidden"
Enter
Sleep 1.5s
Type "Clear-Host"
Enter
Show

# Step 1: Show the deliberate bug failing in tests
Type "Write-Host '=== 1. Running tests on buggy codebase ===' -ForegroundColor Yellow"
Enter
Sleep 500ms
Type "pytest demo/test_calculator.py -k test_calculate_discount"
Enter
Sleep 3s

# Step 2: Run angrist to fix only calculate_discount
Type "Write-Host '=== 2. Running angrist single-function micro-fix ===' -ForegroundColor Cyan"
Enter
Sleep 500ms
Type "$env:ANGRIST_LLM_BASE_URL='http://127.0.0.1:8089'; angrist --file demo/calculator.py --target calculate_discount --instruction 'fix discount calculation by subtracting discount from price' --test-cmd 'pytest demo/test_calculator.py -k test_calculate_discount' --lint-cmd 'python -c pass' --auto-merge"
Enter
Sleep 5s

# Step 3: Verify the test now passes
Type "Write-Host '=== 3. Verifying tests after angrist fix ===' -ForegroundColor Green"
Enter
Sleep 500ms
Type "pytest demo/test_calculator.py -k test_calculate_discount"
Enter
Sleep 3s

# Step 4: Show git diff - only calculate_discount was touched!
Type "Write-Host '=== 4. Git diff showing exact AST scope lock ===' -ForegroundColor Magenta"
Enter
Sleep 500ms
Type "git diff HEAD~1"
Enter
Sleep 4s

# Cleanup background process
Hide
Type "Get-Process python | Where-Object { $_.CommandLine -like '*mock_server*' } | Stop-Process -Force -ErrorAction SilentlyContinue"
Enter
Sleep 500ms
Show
