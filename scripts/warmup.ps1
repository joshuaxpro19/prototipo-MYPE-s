param(
    [string]$Url = "https://prototipo-mype-api.onrender.com"
)

$Url = $Url.TrimEnd("/")
Write-Output "Despertando $Url (los planes gratis tardan hasta 60 s en la primera peticion)..."
$inicio = Get-Date
while ($true) {
    try {
        $r = Invoke-WebRequest "$Url/health" -UseBasicParsing -TimeoutSec 90
        if ($r.StatusCode -eq 200) {
            $seg = [math]::Round(((Get-Date) - $inicio).TotalSeconds, 1)
            Write-Output "Listo en $seg s"
            Write-Output $r.Content
            break
        }
    } catch {
        Start-Sleep -Seconds 5
    }
}
