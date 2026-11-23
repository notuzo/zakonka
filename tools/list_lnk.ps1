$d = [Environment]::GetFolderPath('Desktop')
if (Test-Path $d) {
    Get-ChildItem $d -Filter *.lnk | ForEach-Object {
        $s = (New-Object -ComObject WScript.Shell).CreateShortcut($_.FullName)
        Write-Output ("{0} -> {1} {2}" -f $_.Name, $s.TargetPath, $s.Arguments)
    }
} else {
    Write-Output 'desktop not found'
}
