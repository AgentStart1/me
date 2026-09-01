# Resource metrics collector for the QEMU Alpine Docker plugin.
#
# This PowerShell script runs in the background while a test command executes.
# It periodically samples CPU and memory usage of:
#   - The host machine (via Win32_PerfFormattedData_PerfOS_Processor)
#   - The QEMU process (via Win32_Process.TotalProcessorTime)
#   - The guest VM (via SSH to /proc/stat and /proc/meminfo)
#
# The results are written to a JSON report file when the stop file is created.
# The stop file is written by the parent Bash script (run-testcontainers.sh)
# when the test command finishes.
#
# Communication protocol:
#   - The stop file contains: "<exit_code> <duration_seconds>"
#   - The script reads this when it detects the stop file exists
#   - It writes a JSON report to the report path
#
# The script uses SSH to query the guest for CPU/memory stats.
# It samples CPU usage by comparing /proc/stat between intervals.
# It reads memory usage from /proc/meminfo.
#
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

# Create a new list to store metric samples.
function New-MetricList {
    return ,([System.Collections.Generic.List[double]]::new())
}

# Compute average and peak values from a list of metric samples.
# Returns an ordered dictionary with 'average' and 'peak' keys.
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

# Format a metric value for display. Returns "n/a" if null.
function Format-MetricValue {
    param($Value)
    if ($null -eq $Value) { return "n/a" }
    return $Value.ToString()
}

# --- Metric storage ---
# We store samples as lists of doubles. Each sampling interval adds one value.
# At the end, we compute average and peak from all samples.
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

# --- System information ---
# Collect static system info (logical processors, total memory) for the report.
$computer = Get-CimInstance Win32_ComputerSystem
$operatingSystem = Get-CimInstance Win32_OperatingSystem
$logicalProcessors = [int]$computer.NumberOfLogicalProcessors
$hostTotalMemoryMiB = [math]::Round([double]$operatingSystem.TotalVisibleMemorySize / 1024, 1)

# --- Find the QEMU process ---
# Locate the QEMU process by matching its name and command-line arguments.
# This is necessary because we need to monitor the specific QEMU process
# for the VM being tested (there may be multiple QEMU instances).
$escapedVmName = [regex]::Escape($VmName)
$qemuInfo = Get-CimInstance Win32_Process | Where-Object {
    $_.Name -eq "qemu-system-x86_64.exe" -and
    $_.CommandLine -match "(?:^|\s)-name\s+$escapedVmName(?:\s|$)"
} | Select-Object -First 1
if (-not $qemuInfo) {
    throw "QEMU process for VM '$VmName' was not found."
}

# --- QEMU process initialization ---
# Detect the accelerator type from the QEMU command line.
# Initialize CPU time tracking for the QEMU process (to compute CPU usage).
$accelerator = if ($qemuInfo.CommandLine -match "(?:^|\s)-accel\s+([^\s]+)") { $Matches[1] } else { "unknown" }
$qemuProcess = Get-Process -Id $qemuInfo.ProcessId
$qemuProcess.Refresh()
$previousQemuCpuSeconds = $qemuProcess.TotalProcessorTime.TotalSeconds
$previousQemuSampleTime = Get-Date
$hasQemuCpuSample = $false
# Guest CPU tracking uses /proc/stat; we store previous totals to compute deltas.
$previousGuestTotal = $null
$previousGuestIdle = $null

# --- Main sampling loop ---
# Continuously sample resource usage until the stop file is created by the parent process.
# Each iteration:
#   1. Collects host CPU and memory usage via Win32 APIs
#   2. Computes QEMU process CPU usage from TotalProcessorTime deltas
#   3. Queries the guest via SSH for CPU (/proc/stat) and memory (/proc/meminfo)
#   4. Computes guest CPU usage from /proc/stat deltas
#   5. Stores all samples in lists for later aggregation
#
# The loop catches exceptions (e.g., SSH failures) and continues sampling.
# Errors are counted and reported in the final JSON output.
while (-not (Test-Path -LiteralPath $StopFile)) {
    try {
        $sampleTime = Get-Date
        # --- Host metrics ---
        $processor = Get-CimInstance Win32_PerfFormattedData_PerfOS_Processor -Filter "Name='_Total'"
        $operatingSystem = Get-CimInstance Win32_OperatingSystem
        $hostUsedMemoryMiB = ([double]$operatingSystem.TotalVisibleMemorySize - [double]$operatingSystem.FreePhysicalMemory) / 1024

        # --- QEMU process CPU usage ---
        # We compute the CPU usage by comparing TotalProcessorTime between samples.
        # This is normalized by the number of logical processors and the elapsed time.
        $qemuProcess.Refresh()
        $qemuCpuSeconds = $qemuProcess.TotalProcessorTime.TotalSeconds
        $qemuElapsedSeconds = ($sampleTime - $previousQemuSampleTime).TotalSeconds
        if ($hasQemuCpuSample -and $qemuElapsedSeconds -gt 0) {
            $qemuCpu.Add((($qemuCpuSeconds - $previousQemuCpuSeconds) / $qemuElapsedSeconds / $logicalProcessors) * 100)
        }

        # --- Guest metrics via SSH ---
        # Query the guest for CPU and memory stats in a single SSH call.
        # This is more efficient than separate calls.
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

        # --- Guest CPU usage from /proc/stat ---
        # /proc/stat line format: "cpu <user> <nice> <system> <idle> <iowait> <irq> <softirq> <steal>"
        # We compute the total and idle (idle + iowait) from the first line.
        $cpuFields = @(($guestLines[0] -split "\s+") | Select-Object -Skip 1 | ForEach-Object { [double]$_ })
        $guestTotal = [double](($cpuFields | Measure-Object -Sum).Sum)
        $guestIdle = [double]$cpuFields[3] + [double]$cpuFields[4]
        if ($null -ne $previousGuestTotal -and $guestTotal -gt $previousGuestTotal) {
            $guestCpu.Add((1 - (($guestIdle - $previousGuestIdle) / ($guestTotal - $previousGuestTotal))) * 100)
        }

        # --- Guest memory usage from /proc/meminfo ---
        # MemTotal and MemAvailable are in KiB. We compute used memory as total - available.
        $guestTotalLine = $guestLines | Where-Object { $_ -match "^MemTotal:" } | Select-Object -First 1
        $guestAvailableLine = $guestLines | Where-Object { $_ -match "^MemAvailable:" } | Select-Object -First 1
        if ($guestTotalLine -notmatch "(\d+)") { throw "Guest MemTotal was unavailable." }
        $guestTotalKiB = [double]$Matches[1]
        if ($guestAvailableLine -notmatch "(\d+)") { throw "Guest MemAvailable was unavailable." }
        $guestAvailableKiB = [double]$Matches[1]
        $guestUsedMiB = ($guestTotalKiB - $guestAvailableKiB) / 1024

        # --- Store all samples ---
        $hostCpu.Add([double]$processor.PercentProcessorTime)
        $hostMemoryMiB.Add($hostUsedMemoryMiB)
        $hostMemoryPercent.Add(($hostUsedMemoryMiB / $hostTotalMemoryMiB) * 100)
        $qemuMemoryMiB.Add([double]$qemuProcess.WorkingSet64 / 1MB)
        $guestMemoryMiB.Add($guestUsedMiB)
        $guestMemoryPercent.Add(($guestUsedMiB / ($guestTotalKiB / 1024)) * 100)
        $sampleCount++

        # --- Update previous values for next iteration ---
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

# --- Read stop file and build report ---
# The stop file contains the test command's exit code and duration.
# We parse these and build a structured JSON report.
$stopValues = @((Get-Content -Raw -LiteralPath $StopFile).Trim() -split "\s+")
$commandExitCode = if ($stopValues.Count -ge 1) { [int]$stopValues[0] } else { -1 }
$durationSeconds = if ($stopValues.Count -ge 2) { [int]$stopValues[1] } else { 0 }

# Build the report as an ordered dictionary.
# Using ordered dictionaries ensures the JSON output has a consistent key order.
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

# --- Write the report ---
# Use atomic write (temp file + move) to avoid partial reads.
# The report is written in UTF-8 with depth 6 to support nested objects.
$reportDirectory = Split-Path -Parent $ReportPath
New-Item -ItemType Directory -Path $reportDirectory -Force | Out-Null
$temporaryReport = "$ReportPath.tmp.$PID"
$report | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $temporaryReport -Encoding UTF8
Move-Item -LiteralPath $temporaryReport -Destination $ReportPath -Force

# --- Print summary to stdout ---
# This summary is visible in the terminal and provides a quick overview
# of the resource usage during the test command execution.
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
