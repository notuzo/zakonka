Add-Type -AssemblyName System.Windows.Forms,System.Drawing
Start-Sleep -Seconds 5
$b=[System.Windows.Forms.SystemInformation]::VirtualScreen
$bmp=New-Object System.Drawing.Bitmap($b.Width,$b.Height)
$g=[System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($b.Left,$b.Top,0,0,$bmp.Size)
$bmp.Save("C:\Users\misha\Projects\gta5rp-lawyer\overlay_test.png",[System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose()
$bmp.Dispose()
