param([Parameter(Mandatory)][string]$Executable)
$ErrorActionPreference = 'Stop'
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class PrimeCloudWindow {
    public delegate bool EnumProc(IntPtr window, IntPtr data);
    [DllImport("user32.dll")] static extern bool EnumWindows(EnumProc callback, IntPtr data);
    [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr window, out uint process);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] static extern int GetWindowText(IntPtr window, System.Text.StringBuilder title, int capacity);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] static extern IntPtr FindWindowEx(IntPtr parent, IntPtr after, string cls, string text);
    [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr window, uint msg, IntPtr w, IntPtr l);
    public static IntPtr Player(int pid) {
        IntPtr found = IntPtr.Zero;
        EnumWindows((h,d) => {
            uint owner;
            GetWindowThreadProcessId(h,out owner);
            if (owner != pid) return true;
            var name = new System.Text.StringBuilder(256);
            GetWindowText(h,name,name.Capacity);
            if (name.ToString() != "PrimeCloud") return true;
            if (FindWindowEx(h,IntPtr.Zero,"Edit",null) == IntPtr.Zero ||
                FindWindowEx(h,IntPtr.Zero,"ListBox",null) == IntPtr.Zero) return true;
            found=h; return false;
        },IntPtr.Zero);
        return found;
    }
}
'@
$process = Start-Process (Resolve-Path $Executable) -WindowStyle Hidden -PassThru
try {
    $timer = [Diagnostics.Stopwatch]::StartNew()
    do {
        if ($process.HasExited) { throw "Player exited before opening its window ($($process.ExitCode))" }
        $window = [PrimeCloudWindow]::Player($process.Id)
        if ($window -ne [IntPtr]::Zero) {
            [void][PrimeCloudWindow]::PostMessage($window, 0x10, [IntPtr]::Zero, [IntPtr]::Zero)
            if (!$process.WaitForExit(5000) -or $process.ExitCode -ne 0) { throw "Player did not close normally" }
            Write-Output 'PrimeCloud window, search field and result list verified.'
            return
        }
        Start-Sleep -Milliseconds 100
    } while ($timer.Elapsed.TotalSeconds -lt 10)
    throw 'No PrimeCloud window with a search field and result list appeared.'
} finally {
    if (!$process.HasExited) { $process.Kill() }
    $process.Dispose()
}
