param(
    [Parameter(Mandatory)][string]$Installer,
    [Parameter(Mandatory)][string]$Payload
)

$ErrorActionPreference = 'Stop'
$registrations = @(
    'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\PrimeCloud_is1',
    'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\PrimeCloud_is1',
    'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\PrimeCloud_is1'
)
if ($registrations | Where-Object { Test-Path -LiteralPath $_ }) {
    throw 'Run this test in a Windows account without a PrimeCloud installation'
}

$directory = Join-Path ([IO.Path]::GetTempPath()) "PrimeCloud install test $([guid]::NewGuid())"
$process = Start-Process (Resolve-Path $Installer) -ArgumentList @(
    '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART',
    '/MERGETASKS=!desktopicon,!startmenuicon', ('/DIR="{0}"' -f $directory)
) -WindowStyle Hidden -Wait -PassThru
$uninstaller = Join-Path $directory 'unins000.exe'

try {
    if ($process.ExitCode -ne 0) { throw "Setup exited with code $($process.ExitCode)" }
    $application = Join-Path $directory 'PrimeCloud.exe'
    if ((Get-FileHash $application).Hash -ne (Get-FileHash $Payload).Hash) {
        throw 'Setup installed a different executable'
    }

    & "$PSScriptRoot/test-windows-startup.ps1" $application
} finally {
    if (Test-Path -LiteralPath $uninstaller) {
        $process = Start-Process $uninstaller -ArgumentList '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART' -WindowStyle Hidden -Wait -PassThru
        if ($process.ExitCode -ne 0) { throw "Uninstall exited with code $($process.ExitCode)" }
    }
}

if (Test-Path -LiteralPath $directory) { throw 'The test installation still exists after uninstall' }
Write-Output 'Installed to a custom path, verified the payload and removed the test installation.'
