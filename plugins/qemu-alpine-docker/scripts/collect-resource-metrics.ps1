param(
    [Parameter(Mandatory = $true)]
    [string]$VmName,

    [Parameter(Mandatory = $true)]
    [int]$SshPort,

    [Parameter(Mandatory = $true)]
    [string]$SshKeyPath,

    [Parameter(Mandatory = $true)]
    [string]$StopFile,

    [Parameter(Mandatory = $true)]
    [string]$ReportPath,

    [ValidateRange(1, 60)]
    [int]$IntervalSeconds = 1
)

$ErrorActionPreference = "Stop"

function New-MetricList {
    return ,([System.Collections.Generic.List[double]]::new())
}

function Get-MetricSummary {
    param([System.Collections.Generic.List[double]]$Values)

    if ($Values.Count -eq 0) {
        return [ordered]@{ average = $null; peak = $null }
    }

    $measurement = $Values | Measure-Object -Average -Maximum
    return [ordered]@{
        average = [math]::Round([double]$measurement.Average, 1)
        peak = [math]::Round([double]$measurement.Maximum, 1)
    }
}

function Format-MetricValue {
    param($Value)
    if ($null -eq $Value) { return "n/a" }
    return $Value.ToString()
}

$hostCpu = New-MetricList
$hostMemoryMiB = New-MetricList
$hostMemoryPercent = New-MetricList
$qemuCpu = New-MetricList
$qemuMemoryMiB = New-MetricList
$guestCpu = New-MetricList
$guestMemoryMiB = New-MetricList
$guestMemoryPercent = New-MetricList
$sampleCount = 0
$samplingErrors = 0
$firstSamplingError = $null

$computer = Get-CimInstance Win32_ComputerSystem
$operatingSystem = Get-CimInstance Win32_OperatingSystem
$logicalProcessors = [int]$computer.NumberOfLogicalProcessors
$hostTotalMemoryMiB = [math]::Round([double]$operatingSystem.TotalVisibleMemorySize / 1024, 1)

$escapedVmName = [regex]::Escape($VmName)
$qemuInfo = Get-CimInstance Win32_Process | Where-Object {
    $_.Name -eq "qemu-system-x86_64.exe" -and
    $_.CommandLine -match "(?:^|\s)-name\s+$escapedVmName(?:\s|$)"
} | Select-Object -First 1
if (-not $qemuInfo) {
    throw "QEMU process for VM '$VmName' was not found."
}

$accelerator = if ($qemuInfo.CommandLine -match "(?:^|\s)-accel\s+([^\s]+)") { $Matches[1] } else { "unknown" }
$qemuProcess = Get-Process -Id $qemuInfo.ProcessId
$qemuProcess.Refresh()
$previousQemuCpuSeconds = $qemuProcess.TotalProcessorTime.TotalSeconds
$previousQemuSampleTime = Get-Date
$hasQemuCpuSample = $false
$previousGuestTotal = $null
$previousGuestIdle = $null

while (-not (Test-Path -LiteralPath $StopFile)) {
    try {
        $sampleTime = Get-Date
        $processor = Get-CimInstance Win32_PerfFormattedData_PerfOS_Processor -Filter "Name='_Total'"
        $operatingSystem = Get-CimInstance Win32_OperatingSystem
        $hostUsedMemoryMiB = ([double]$operatingSystem.TotalVisibleMemorySize - [double]$operatingSystem.FreePhysicalMemory) / 1024

        $qemuProcess.Refresh()
        $qemuCpuSeconds = $qemuProcess.TotalProcessorTime.TotalSeconds
        $qemuElapsedSeconds = ($sampleTime - $previousQemuSampleTime).TotalSeconds
        if ($hasQemuCpuSample -and $qemuElapsedSeconds -gt 0) {
            $qemuCpu.Add((($qemuCpuSeconds - $previousQemuCpuSeconds) / $qemuElapsedSeconds / $logicalProcessors) * 100)
        }

        $sshArguments = @(
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=NUL",
            "-o", "LogLevel=ERROR",
            "-o", "ConnectTimeout=3",
            "-p", $SshPort,
            "-i", $SshKeyPath,
            "root@127.0.0.1",
            "head -n 1 /proc/stat; grep -E '^(MemTotal|MemAvailable):' /proc/meminfo"
        )
        $guestLines = @(& ssh.exe @sshArguments)
        if ($LASTEXITCODE -ne 0 -or $guestLines.Count -lt 3) {
            throw "Guest resource query failed with exit code $LASTEXITCODE."
        }

        $cpuFields = @(($guestLines[0] -split "\s+") | Select-Object -Skip 1 | ForEach-Object { [double]$_ })
        $guestTotal = [double](($cpuFields | Measure-Object -Sum).Sum)
        $guestIdle = [double]$cpuFields[3] + [double]$cpuFields[4]
        if ($null -ne $previousGuestTotal -and $guestTotal -gt $previousGuestTotal) {
            $guestCpu.Add((1 - (($guestIdle - $previousGuestIdle) / ($guestTotal - $previousGuestTotal))) * 100)
        }

        $guestTotalLine = $guestLines | Where-Object { $_ -match "^MemTotal:" } | Select-Object -First 1
        $guestAvailableLine = $guestLines | Where-Object { $_ -match "^MemAvailable:" } | Select-Object -First 1
        if ($guestTotalLine -notmatch "(\d+)") { throw "Guest MemTotal was unavailable." }
        $guestTotalKiB = [double]$Matches[1]
        if ($guestAvailableLine -notmatch "(\d+)") { throw "Guest MemAvailable was unavailable." }
        $guestAvailableKiB = [double]$Matches[1]
        $guestUsedMiB = ($guestTotalKiB - $guestAvailableKiB) / 1024

        $hostCpu.Add([double]$processor.PercentProcessorTime)
        $hostMemoryMiB.Add($hostUsedMemoryMiB)
        $hostMemoryPercent.Add(($hostUsedMemoryMiB / $hostTotalMemoryMiB) * 100)
        $qemuMemoryMiB.Add([double]$qemuProcess.WorkingSet64 / 1MB)
        $guestMemoryMiB.Add($guestUsedMiB)
        $guestMemoryPercent.Add(($guestUsedMiB / ($guestTotalKiB / 1024)) * 100)
        $sampleCount++

        $previousQemuCpuSeconds = $qemuCpuSeconds
        $previousQemuSampleTime = $sampleTime
        $hasQemuCpuSample = $true
        $previousGuestTotal = $guestTotal
        $previousGuestIdle = $guestIdle
    }
    catch {
        $samplingErrors++
        if (-not $firstSamplingError) { $firstSamplingError = $_.Exception.Message }
    }

    Start-Sleep -Seconds $IntervalSeconds
}

$stopValues = @((Get-Content -Raw -LiteralPath $StopFile).Trim() -split "\s+")
$commandExitCode = if ($stopValues.Count -ge 1) { [int]$stopValues[0] } else { -1 }
$durationSeconds = if ($stopValues.Count -ge 2) { [int]$stopValues[1] } else { 0 }

$report = [ordered]@{
    generatedAt = (Get-Date).ToUniversalTime().ToString("o")
    command = [ordered]@{
        durationSeconds = $durationSeconds
        exitCode = $commandExitCode
    }
    sampling = [ordered]@{
        intervalSeconds = $IntervalSeconds
        samples = $sampleCount
        errors = $samplingErrors
        firstError = $firstSamplingError
    }
    host = [ordered]@{
        logicalProcessors = $logicalProcessors
        totalMemoryMiB = $hostTotalMemoryMiB
        cpuPercent = Get-MetricSummary $hostCpu
        memoryUsedMiB = Get-MetricSummary $hostMemoryMiB
        memoryUsedPercent = Get-MetricSummary $hostMemoryPercent
    }
    qemu = [ordered]@{
        accelerator = $accelerator
        cpuPercent = Get-MetricSummary $qemuCpu
        workingSetMiB = Get-MetricSummary $qemuMemoryMiB
    }
    guest = [ordered]@{
        cpuPercent = Get-MetricSummary $guestCpu
        memoryUsedMiB = Get-MetricSummary $guestMemoryMiB
        memoryUsedPercent = Get-MetricSummary $guestMemoryPercent
    }
}

$reportDirectory = Split-Path -Parent $ReportPath
New-Item -ItemType Directory -Path $reportDirectory -Force | Out-Null
$temporaryReport = "$ReportPath.tmp.$PID"
$report | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $temporaryReport -Encoding UTF8
Move-Item -LiteralPath $temporaryReport -Destination $ReportPath -Force

$hostCpuSummary = $report.host.cpuPercent
$hostMemorySummary = $report.host.memoryUsedMiB
$qemuCpuSummary = $report.qemu.cpuPercent
$qemuMemorySummary = $report.qemu.workingSetMiB
$guestCpuSummary = $report.guest.cpuPercent
$guestMemorySummary = $report.guest.memoryUsedMiB

Write-Output "Resource metrics: samples=$sampleCount errors=$samplingErrors interval=${IntervalSeconds}s accelerator=$accelerator"
Write-Output ("  Host  CPU avg/peak: {0}% / {1}%; memory avg/peak: {2} / {3} MiB" -f (Format-MetricValue $hostCpuSummary.average), (Format-MetricValue $hostCpuSummary.peak), (Format-MetricValue $hostMemorySummary.average), (Format-MetricValue $hostMemorySummary.peak))
Write-Output ("  QEMU  CPU avg/peak: {0}% / {1}%; memory avg/peak: {2} / {3} MiB" -f (Format-MetricValue $qemuCpuSummary.average), (Format-MetricValue $qemuCpuSummary.peak), (Format-MetricValue $qemuMemorySummary.average), (Format-MetricValue $qemuMemorySummary.peak))
Write-Output ("  Guest CPU avg/peak: {0}% / {1}%; memory avg/peak: {2} / {3} MiB" -f (Format-MetricValue $guestCpuSummary.average), (Format-MetricValue $guestCpuSummary.peak), (Format-MetricValue $guestMemorySummary.average), (Format-MetricValue $guestMemorySummary.peak))
Write-Output "  Command duration/exit: ${durationSeconds}s / $commandExitCode"
Write-Output "  Report: $ReportPath"
