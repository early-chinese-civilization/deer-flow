param(
    [switch]$TestMode
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$stopPorts = @(3000, 8001, 2024, 2026)
$stoppedPatterns = @(
    "uvicorn app.gateway.app:app",
    "langgraph dev",
    "scripts/langgraph_windows.py",
    "next dev",
    "next start",
    "next-server",
    "nginx"
)
$cleanupContainer = "deer-flow-sandbox"

if ($TestMode) {
    @{
        script = "stop-windows.ps1"
        ports = $stopPorts
        stopped_patterns = $stoppedPatterns
        cleanup_container = $cleanupContainer
    } | ConvertTo-Json -Compress
    exit 0
}

function Get-AllProcesses {
    @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
}

function Get-TrackedProcessIds {
    param(
        [object[]]$Processes
    )

    $ids = New-Object System.Collections.Generic.HashSet[int]

    foreach ($process in $Processes) {
        $commandLine = ""
        if ($null -ne $process.CommandLine) {
            $commandLine = [string]$process.CommandLine
        }
        $name = ""
        if ($null -ne $process.Name) {
            $name = [string]$process.Name
        }
        $processId = [int]$process.ProcessId

        if (
            $commandLine -like "*uvicorn*app.gateway.app:app*" -or
            $commandLine -like "*langgraph dev*" -or
            $commandLine -like "*scripts/langgraph_windows.py*" -or
            $commandLine -like "*next dev*" -or
            $commandLine -like "*next start*" -or
            $commandLine -like "*next-server*" -or
            $commandLine -like "*nginx.local.conf*" -or
            (($commandLine -like "*$repoRoot*") -and $name -ieq "nginx.exe")
        ) {
            $null = $ids.Add($processId)
        }
    }

    foreach ($port in $stopPorts) {
        $listeners = @(Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue)
        foreach ($listener in $listeners) {
            $null = $ids.Add([int]$listener.OwningProcess)
        }
    }

    $ids
}

function Expand-ProcessTree {
    param(
        [object[]]$Processes,
        [System.Collections.Generic.HashSet[int]]$RootIds
    )

    $childrenByParent = @{}
    foreach ($process in $Processes) {
        $parentId = 0
        if ($null -ne $process.ParentProcessId) {
            $parentId = [int]$process.ParentProcessId
        }
        if (-not $childrenByParent.ContainsKey($parentId)) {
            $childrenByParent[$parentId] = New-Object System.Collections.Generic.List[int]
        }
        $childrenByParent[$parentId].Add([int]$process.ProcessId)
    }

    $allIds = New-Object System.Collections.Generic.HashSet[int]
    $depthById = @{}
    $queue = New-Object System.Collections.Generic.Queue[object]

    foreach ($rootId in $RootIds) {
        if ($rootId -le 0) {
            continue
        }
        if ($allIds.Add($rootId)) {
            $depthById[$rootId] = 0
            $queue.Enqueue([pscustomobject]@{ Id = $rootId; Depth = 0 })
        }
    }

    while ($queue.Count -gt 0) {
        $current = $queue.Dequeue()
        $childIds = @($childrenByParent[[int]$current.Id])
        foreach ($childId in $childIds) {
            $childPid = [int]$childId
            if ($allIds.Add($childPid)) {
                $depth = [int]$current.Depth + 1
                $depthById[$childPid] = $depth
                $queue.Enqueue([pscustomobject]@{ Id = $childPid; Depth = $depth })
            }
        }
    }

    [pscustomobject]@{
        AllIds = $allIds
        DepthById = $depthById
    }
}

function Stop-TrackedProcesses {
    param(
        [System.Collections.Generic.HashSet[int]]$Ids,
        [hashtable]$DepthById
    )

    $ordered = @(
        $Ids | Sort-Object {
            if ($DepthById.ContainsKey($_)) {
                return [int]$DepthById[$_]
            }
            return 0
        } -Descending
    )

    $currentProcessId = $PID

    foreach ($targetProcessId in $ordered) {
        if ($targetProcessId -le 0 -or $targetProcessId -eq $currentProcessId) {
            continue
        }
        Stop-Process -Id $targetProcessId -Force -ErrorAction SilentlyContinue
    }
}

function Wait-PortsToClose {
    foreach ($attempt in 1..20) {
        $openPorts = @()
        foreach ($port in $stopPorts) {
            $listeners = @(Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue)
            if ($listeners.Count -gt 0) {
                $openPorts += $port
            }
        }
        if ($openPorts.Count -eq 0) {
            return
        }
        Start-Sleep -Milliseconds 300
    }
}

function Invoke-SandboxCleanup {
    $wrapperPath = Join-Path $repoRoot "scripts\\run-with-git-bash.cmd"
    if (-not (Test-Path $wrapperPath)) {
        return
    }

    try {
        Start-Process `
            -FilePath "cmd.exe" `
            -ArgumentList "/c", "call scripts\\run-with-git-bash.cmd ./scripts/cleanup-containers.sh $cleanupContainer" `
            -WorkingDirectory $repoRoot `
            -NoNewWindow `
            -Wait | Out-Null
    } catch {
        Write-Host "Sandbox cleanup skipped: $($_.Exception.Message)"
    }
}

Write-Host "Stopping all services..."
$allProcesses = Get-AllProcesses
$rootIds = Get-TrackedProcessIds -Processes $allProcesses
$expanded = Expand-ProcessTree -Processes $allProcesses -RootIds $rootIds
Stop-TrackedProcesses -Ids $expanded.AllIds -DepthById $expanded.DepthById
Wait-PortsToClose
Write-Host "Cleaning up sandbox containers..."
Invoke-SandboxCleanup
Write-Host "All services stopped"
