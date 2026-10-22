$ErrorActionPreference = 'Stop'
$root = 'C:\ProgramData\qemu-guests'
# The assembly is compiled on the host; loading it never invokes a guest compiler.
Add-Type -Path "$root\appium\desktop-helper.dll"
$screen = [GuestDesktop.Display]::Configure({{WIDTH}}, {{HEIGHT}})
$screen | ConvertTo-Json -Compress | Set-Content -LiteralPath "$root\desktop-ready.json" -Encoding ascii
