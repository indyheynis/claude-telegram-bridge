<#
  Start the bridge (bridge.py) automatically and invisibly when you log on to Windows.

  Enable:   powershell -ExecutionPolicy Bypass -File autostart.ps1
  Disable:  powershell -ExecutionPolicy Bypass -File autostart.ps1 -Uninstall

  What the scheduled task does:
  - starts 30 seconds after logon (so the network is up);
  - runs invisibly (pythonw.exe, no console window);
  - watchdog: every 3 minutes Windows checks whether the bridge still runs and starts it if not
    (tested: Task Scheduler's "restart on failure" does NOT help when the program crashes later);
  - also runs on battery and has no time limit;
  - never runs twice at the same time.
#>
param([switch]$Uninstall, [switch]$Verwijder)

$TaskName = "Claude Telegram Bridge"
$OldTaskNames = @("Claude Telegram Postbode")  # earlier (Dutch) name
$Project = $PSScriptRoot

foreach ($old in $OldTaskNames) {
    if (Get-ScheduledTask -TaskName $old -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $old -Confirm:$false
        Write-Output "Removed old task '$old'."
    }
}

if ($Uninstall -or $Verwijder) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Output "Task '$TaskName' removed. The bridge no longer starts by itself."
    exit 0
}

$Pythonw = Join-Path $Project ".venv\Scripts\pythonw.exe"
if (-not (Test-Path $Pythonw)) {
    Write-Output "Not found: $Pythonw. Run 'uv sync' in $Project first."
    exit 1
}

$User = "$env:USERDOMAIN\$env:USERNAME"
$Action = New-ScheduledTaskAction -Execute $Pythonw -Argument "-X utf8 bridge.py" -WorkingDirectory $Project
$AtLogon = New-ScheduledTaskTrigger -AtLogOn -User $User
$AtLogon.Delay = "PT30S"
# Watchdog: every 3 minutes. If the bridge is already running this does nothing (MultipleInstances IgnoreNew).
$Watchdog = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 3)
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -StartWhenAvailable -MultipleInstances IgnoreNew
$Principal = New-ScheduledTaskPrincipal -UserId $User -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger @($AtLogon, $Watchdog) -Settings $Settings `
    -Principal $Principal -Description "Starts the Claude Telegram bridge (bridge.py) at logon." -Force | Out-Null
Write-Output "Task '$TaskName' created. The bridge now starts 30 seconds after logon (watchdog every 3 minutes)."
