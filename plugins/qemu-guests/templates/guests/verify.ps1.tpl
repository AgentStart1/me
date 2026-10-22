$ErrorActionPreference = 'Stop'
if (-not (Test-Path 'C:\ProgramData\qemu-guests\bootstrap-ready.txt')) { throw 'Bootstrap incomplete' }
if (Test-Path 'C:\ProgramData\qemu-guests\desktop.json') {
    $expected = Get-Content -Raw 'C:\ProgramData\qemu-guests\desktop.json' | ConvertFrom-Json
    $actual = Get-Content -Raw 'C:\ProgramData\qemu-guests\desktop-ready.json' | ConvertFrom-Json
    if ($actual.Width -ne $expected.width -or $actual.Height -ne $expected.height -or $actual.Dpi -ne 96) { throw 'Desktop initialization incomplete' }
}
$client = New-Object System.Net.WebClient
$client.Proxy = $null
$status = $client.DownloadString('http://127.0.0.1:4723/status') | ConvertFrom-Json
if (-not $status.value.ready) { throw 'Appium is not ready in the guest desktop session' }
