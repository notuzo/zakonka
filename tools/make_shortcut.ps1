$project = 'C:\Users\misha\Projects\gta5rp-lawyer'
$pythonw = 'C:\Users\misha\AppData\Local\Programs\Python\Python310\pythonw.exe'
$desktop = [Environment]::GetFolderPath('Desktop')
$lnk = Join-Path $desktop 'Zakonka.lnk'
$ws = New-Object -ComObject WScript.Shell
$s = $ws.CreateShortcut($lnk)
$s.TargetPath = $pythonw
$s.Arguments = '"' + $project + '\overlay.py"'
$s.WorkingDirectory = $project
$s.IconLocation = $pythonw + ',0'
$s.WindowStyle = 1
$s.Description = 'Zakonka GTA5RP'
$s.Save()
Write-Output $lnk
