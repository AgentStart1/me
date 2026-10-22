$ErrorActionPreference = 'Stop'
$root = 'C:\ProgramData\qemu-guests'
$env:APPIUM_HOME = "$root\appium\extensions"
Set-Location $root
if (Test-Path "$root\desktop.json") {
    & "$root\desktop-setup.ps1"
}
$arguments = '"' + "$root\appium-run.cjs" + '"'
$process = Start-Process -FilePath "$root\appium\node.exe" -ArgumentList $arguments -NoNewWindow -Wait -PassThru -RedirectStandardOutput "$root\appium-startup.log" -RedirectStandardError "$root\appium-error.log"
exit $process.ExitCode
