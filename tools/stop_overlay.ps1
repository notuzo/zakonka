Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'" |
    Where-Object { $_.CommandLine -like '*overlay.py*' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
Remove-Item "C:\Users\misha\Projects\gta5rp-lawyer\overlay.lock" -ErrorAction SilentlyContinue
