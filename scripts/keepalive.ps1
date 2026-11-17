param(
    [string]$Distro = "Ubuntu-24.04",
    [int]$Horas = 24
)

$running = (wsl.exe -l --running) -join " "
if ($running -match [regex]::Escape($Distro)) {
    Write-Output "La distro $Distro ya esta corriendo; el stack no se detendra por inactividad."
    exit 0
}

$segundos = [string]($Horas * 3600)
Start-Process -FilePath "wsl.exe" -ArgumentList "-d", $Distro, "-e", "sleep", $segundos -WindowStyle Hidden
Write-Output "Keepalive iniciado en $Distro por $Horas h (sleep $segundos)."
Write-Output "Para detenerlo: wsl --shutdown"
