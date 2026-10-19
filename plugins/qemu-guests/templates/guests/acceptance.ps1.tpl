$ErrorActionPreference = 'Stop'
$work = Join-Path $env:TEMP ('qemu-guests-{{TOKEN}}')
$image = 'qemu-guests-validation:{{TOKEN}}'
$container = $null
New-Item -ItemType Directory $work | Out-Null
Push-Location $work
try {
    Set-Content -LiteralPath Dockerfile -Encoding ascii -Value @('FROM busybox:1.37','COPY index.html /www/index.html','CMD ["httpd", "-f", "-p", "8080", "-h", "/www"]')
    Set-Content -LiteralPath index.html -Encoding ascii -NoNewline -Value '{{TOKEN}}'
    docker build -t $image .
    if ($LASTEXITCODE) { throw 'Guest Docker context build failed' }
    $container = docker run -d --rm --label com.me.qemu-guests.validation={{TOKEN}} -p {{PORT}}:8080 $image
    if ($LASTEXITCODE) { throw 'Guest Docker container creation failed' }
    $web = New-Object System.Net.WebClient
    $web.Proxy = $null
    if (($web.DownloadString('http://127.0.0.1:2375/version') | ConvertFrom-Json).Os -ne 'linux') { throw 'Guest Docker API is not the shared Linux daemon' }
    for ($attempt=0; $attempt -lt 30; $attempt++) {
        try {
            if ($web.DownloadString('http://127.0.0.1:{{PORT}}') -ne '{{TOKEN}}') { throw 'Unexpected published response' }
            break
        } catch { if ($attempt -eq 29) { throw }; Start-Sleep -Milliseconds 200 }
    }
    Write-Output CLI_BUILD_API_PUBLISHED_PORT_OK
} finally {
    if ($container) { docker rm -f $container | Out-Null }
    docker image rm $image | Out-Null
    Pop-Location
    $tempRoot = [IO.Path]::GetFullPath($env:TEMP).TrimEnd('\') + '\'
    $resolvedWork = [IO.Path]::GetFullPath($work)
    if (-not $resolvedWork.StartsWith($tempRoot, [StringComparison]::OrdinalIgnoreCase)) { throw 'Validation cleanup path escaped TEMP' }
    Remove-Item -LiteralPath $work -Recurse -Force
}
