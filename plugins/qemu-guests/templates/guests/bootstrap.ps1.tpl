$ErrorActionPreference = 'Stop'
$root = 'C:\ProgramData\qemu-guests'
New-Item -ItemType Directory -Force $root | Out-Null
$seed = Get-Volume | Where-Object FileSystemLabel -eq GUESTSEED | Select-Object -First 1
if (-not $seed.DriveLetter) { throw 'Missing guest seed media' }
Expand-Archive -LiteralPath ($seed.DriveLetter + ':\payload.zip') -DestinationPath $root -Force
Add-WindowsCapability -Online -Name OpenSSH.Client~~~~0.0.1.0 | Out-Null
Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0 | Out-Null
$sshDir = 'C:\ProgramData\ssh'
New-Item -ItemType Directory -Force $sshDir | Out-Null
Set-Content -LiteralPath "$sshDir\administrators_authorized_keys" -Value '{{PUBLIC_KEY}}' -Encoding ascii
icacls "$sshDir\administrators_authorized_keys" /inheritance:r /grant '*S-1-5-18:F' '*S-1-5-32-544:F' | Out-Null
$account = New-Object System.Security.Principal.NTAccount($env:COMPUTERNAME, '{{USER}}')
$userSid = $account.Translate([System.Security.Principal.SecurityIdentifier]).Value
icacls "$root\backend-key" /inheritance:r /grant:r "*${userSid}:R" '*S-1-5-18:F' | Out-Null
icacls "$root\backend-key" /setowner "*$userSid" | Out-Null
icacls "$root\backend-tunnel-key" /inheritance:r /grant:r '*S-1-5-18:F' | Out-Null
icacls "$root\backend-tunnel-key" /setowner '*S-1-5-18' | Out-Null
Set-Service sshd -StartupType Automatic
Start-Service sshd
if (-not (Get-NetFirewallRule -Name OpenSSH-Server-In-TCP -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -Name OpenSSH-Server-In-TCP -DisplayName 'QEMU Guests SSH' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 22 -Profile Any | Out-Null
}
Set-NetFirewallRule -Name OpenSSH-Server-In-TCP -Enabled True -Profile Any
$variables = @{
    QEMU_DOCKER_SSH_HOST='10.0.2.2'; QEMU_DOCKER_SSH_PORT='{{SSH_PORT}}'; QEMU_DOCKER_SSH_KEY="$root\backend-key"
    DOCKER_HOST='tcp://127.0.0.1:2375'; TESTCONTAINERS_HOST_OVERRIDE='127.0.0.1'
    TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE='/var/run/docker.sock'
    TESTCONTAINERS_PULL_PAUSE_TIMEOUT='300'; TESTCONTAINERS_PULL_TIMEOUT='1800'
}
foreach ($name in $variables.Keys) { [Environment]::SetEnvironmentVariable($name, $variables[$name], 'Machine') }
foreach ($name in @('DOCKER_TLS_VERIFY','DOCKER_CERT_PATH','TESTCONTAINERS_RYUK_DISABLED')) {
    [Environment]::SetEnvironmentVariable($name, $null, 'Machine')
}
$machinePath = [Environment]::GetEnvironmentVariable('Path','Machine')
if ($machinePath.Split(';') -notcontains $root) { [Environment]::SetEnvironmentVariable('Path', "$root;$machinePath", 'Machine') }
$ssh = "$env:WINDIR\System32\OpenSSH\ssh.exe"
$arguments = @({{PS_TUNNEL_ARGS}}) | ForEach-Object { if ($_ -eq 'UserKnownHostsFile=/dev/null') { 'UserKnownHostsFile=NUL' } else { $_ } }
$action = New-ScheduledTaskAction -Execute $ssh -Argument ($arguments -join ' ')
$trigger = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero)
Register-ScheduledTask -TaskName QemuGuestsDocker -Action $action -Trigger $trigger -Settings $settings -User SYSTEM -RunLevel Highest -Force | Out-Null
Start-ScheduledTask QemuGuestsDocker
# New SSH sessions inherit the persisted machine environment after reboot.
$configuredBoot = (Get-CimInstance Win32_OperatingSystem).LastBootUpTime.ToUniversalTime().ToString('o')
Set-Content -LiteralPath "$root\bootstrap-boot.txt" -Value $configuredBoot -Encoding ascii
Restart-Computer -Force
