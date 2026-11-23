$sh = New-Object -ComObject WScript.Shell
$lnk = 'C:\Users\misha\Desktop\Zakonka.lnk'
$s = $sh.CreateShortcut($lnk)
$s.IconLocation = 'C:\Users\misha\Projects\gta5rp-lawyer\logo.ico,0'
$s.Save()
$s.TargetPath
$s.IconLocation
