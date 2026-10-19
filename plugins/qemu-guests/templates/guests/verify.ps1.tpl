$ErrorActionPreference = 'Stop'
$marker = 'C:\ProgramData\qemu-guests\bootstrap-boot.txt'
if (-not (Test-Path -LiteralPath $marker)) { throw 'Windows bootstrap has not completed' }
$configuredBoot = [DateTime]::Parse((Get-Content -LiteralPath $marker -Raw)).ToUniversalTime()
if ((Get-CimInstance Win32_OperatingSystem).LastBootUpTime.ToUniversalTime() -le $configuredBoot) {
    throw 'Waiting for the final bootstrap reboot'
}
& C:\ProgramData\qemu-guests\docker.exe version
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$client = New-Object System.Net.WebClient
$client.Proxy = $null
$version = $client.DownloadString('http://127.0.0.1:2375/version') | ConvertFrom-Json
if ($version.Os -ne 'linux') { throw 'Expected Alpine Linux Docker backend' }
foreach ($port in {{POOL_START}}..{{POOL_END}}) {
    $socket = New-Object System.Net.Sockets.TcpClient
    try {
        $result = $socket.BeginConnect('127.0.0.1', $port, $null, $null)
        if (-not $result.AsyncWaitHandle.WaitOne(1000)) { throw 'Missing published-port listener' }
        $socket.EndConnect($result)
    } finally { $socket.Dispose() }
}
