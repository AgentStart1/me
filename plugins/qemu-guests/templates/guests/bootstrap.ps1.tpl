$ErrorActionPreference = 'Stop'
$env:TEST_DESKTOP_USER = '{{USER}}'
$root = 'C:\ProgramData\qemu-guests'
New-Item -ItemType Directory -Force $root | Out-Null
# Supports upgrading an existing guest after copying the new payload here.
if (-not (Test-Path "$root\appium-runtime.zip")) {
    $seed = Get-Volume | Where-Object FileSystemLabel -eq GUESTSEED | Select-Object -First 1
    if (-not $seed.DriveLetter) { throw 'Missing guest seed media' }
    Expand-Archive -LiteralPath ($seed.DriveLetter + ':\payload.zip') -DestinationPath $root -Force
}
Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0 | Out-Null
$sshDir = 'C:\ProgramData\ssh'
New-Item -ItemType Directory -Force $sshDir | Out-Null
Set-Content -LiteralPath "$sshDir\administrators_authorized_keys" -Value '{{PUBLIC_KEY}}' -Encoding ascii
icacls "$sshDir\administrators_authorized_keys" /inheritance:r /grant '*S-1-5-18:F' '*S-1-5-32-544:F' | Out-Null
Set-Service sshd -StartupType Automatic
Start-Service sshd
if (-not (Get-NetFirewallRule -Name OpenSSH-Server-In-TCP -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -Name OpenSSH-Server-In-TCP -DisplayName 'QEMU Guests SSH' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 22 -Profile Any | Out-Null
}
Set-NetFirewallRule -Name OpenSSH-Server-In-TCP -Enabled True -Profile Any
# Remove only the former plugin-owned Docker task, credentials and environment.
$old = Get-ScheduledTask -TaskName QemuGuestsDocker -ErrorAction SilentlyContinue
if ($old) {
    Stop-ScheduledTask -TaskName QemuGuestsDocker
    Unregister-ScheduledTask -TaskName QemuGuestsDocker -Confirm:$false
}
foreach ($name in @('backend-key','backend-tunnel-key','docker.exe','environment')) {
    Remove-Item -LiteralPath "$root\$name" -Force -ErrorAction SilentlyContinue
}
foreach ($name in @('QEMU_DOCKER_SSH_HOST','QEMU_DOCKER_SSH_PORT','QEMU_DOCKER_SSH_KEY','DOCKER_HOST','TESTCONTAINERS_HOST_OVERRIDE','TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE','TESTCONTAINERS_PULL_PAUSE_TIMEOUT','TESTCONTAINERS_PULL_TIMEOUT')) {
    [Environment]::SetEnvironmentVariable($name, $null, 'Machine')
}
Expand-Archive -LiteralPath "$root\appium-runtime.zip" -DestinationPath "$root\appium" -Force
& "$root\appium\node.exe" "$root\relocate-runtime.cjs"
if ($LASTEXITCODE -ne 0) { throw 'Appium runtime preparation failed' }
if (Test-Path "$root\setup-hooks.json") {
    & "$root\appium\node.exe" "$root\run-setup-hooks.cjs"
    if ($LASTEXITCODE -ne 0) { throw 'Project runtime initialization failed; inspect private setup-logs' }
}
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument '-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File C:\ProgramData\qemu-guests\appium.ps1'
$trigger = New-ScheduledTaskTrigger -AtLogOn -User '{{USER}}'
$principal = New-ScheduledTaskPrincipal -UserId '{{USER}}' -LogonType Interactive -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero)
Register-ScheduledTask -TaskName QemuGuestsAppium -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
$logon = 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon'
if (Test-Path "$root\account-password") {
    Set-ItemProperty $logon DefaultPassword (Get-Content -Raw -LiteralPath "$root\account-password")
    Remove-Item -LiteralPath "$root\account-password" -Force
}
Set-ItemProperty $logon DefaultUserName '{{USER}}'
Set-ItemProperty $logon DefaultDomainName $env:COMPUTERNAME
Set-ItemProperty $logon AutoAdminLogon '1'
Remove-ItemProperty $logon AutoLogonCount -ErrorAction SilentlyContinue
powercfg.exe /change monitor-timeout-ac 0
powercfg.exe /change standby-timeout-ac 0
Set-Content -LiteralPath "$root\bootstrap-ready.txt" -Value 'Appium test environment' -Encoding ascii
if (Test-Path "$root\desktop.json") {
    if (-not (Test-Path "$root\appium\desktop-helper.dll")) { throw 'Prepare the desktop helper on the host before installation' }
    New-ItemProperty 'HKCU:\Control Panel\Desktop' -Name LogPixels -PropertyType DWord -Value 96 -Force | Out-Null
    New-ItemProperty 'HKCU:\Control Panel\Desktop' -Name Win8DpiScaling -PropertyType DWord -Value 1 -Force | Out-Null
    New-ItemProperty 'HKCU:\Control Panel\Desktop\WindowMetrics' -Name AppliedDPI -PropertyType DWord -Value 96 -Force | Out-Null
    Restart-Computer -Force
} else {
    Start-ScheduledTask QemuGuestsAppium
}
