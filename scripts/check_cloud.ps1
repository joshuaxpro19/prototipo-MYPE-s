param(
    [string]$Api = "https://prototipo-mype-api.onrender.com",
    [string]$Email = "propietario@mype.pe",
    [string]$Password = "Piloto2026!",
    [int]$EsperaSeg = 120
)

$Api = $Api.TrimEnd("/")
$ErrorActionPreference = "Stop"

function Paso($texto) { Write-Host ""; Write-Host $texto -ForegroundColor Cyan }

Paso "1. /health (el plan free duerme; el primer intento puede tardar ~1 min)"
$reloj = [Diagnostics.Stopwatch]::StartNew()
$health = $null
while ($reloj.Elapsed.TotalSeconds -lt $EsperaSeg) {
    try { $health = Invoke-RestMethod "$Api/health" -TimeoutSec 90; break } catch { Start-Sleep -Seconds 5 }
}
if (-not $health) { Write-Host "  X no respondio en $EsperaSeg s" -ForegroundColor Red; exit 1 }
Write-Host ("  OK en {0:N0} s -> {1}" -f $reloj.Elapsed.TotalSeconds, ($health | ConvertTo-Json -Compress)) -ForegroundColor Green

Paso "2. codigo de acceso (DEMO_MODE)"
$code = $null
try {
    $code = Invoke-RestMethod "$Api/api/v1/auth/demo-code" -TimeoutSec 20
    Write-Host "  OK $($code.email) - OTP $($code.otp) (vence en $($code.expira_en) s)" -ForegroundColor Green
} catch {
    Write-Host "  ! /auth/demo-code no disponible: revisa DEMO_MODE=1 en Render" -ForegroundColor Yellow
    exit 0
}

Paso "3. login MFA"
$body = @{ email = $code.email; password = $Password; otp = $code.otp } | ConvertTo-Json
try {
    $login = Invoke-RestMethod "$Api/api/v1/auth/login" -Method Post -Body $body -ContentType "application/json" -TimeoutSec 20
    Write-Host "  OK rol=$($login.role)" -ForegroundColor Green
} catch {
    Write-Host "  X $($_.Exception.Message) - revisa ADMIN_PASSWORD" -ForegroundColor Red
    exit 1
}
$h = @{ Authorization = "Bearer $($login.access_token)" }

Paso "4. endpoints del panel"
$dash = Invoke-RestMethod "$Api/api/v1/dashboard" -Headers $h -TimeoutSec 20
Write-Host ("  dashboard : SKUs {0} / MAPE {1} / F1 {2} / silueta {3}" -f $dash.skus_monitoreados, $dash.mape, $dash.f1_quiebre, $dash.silueta)
$mods = Invoke-RestMethod "$Api/api/v1/models" -Headers $h -TimeoutSec 20
Write-Host ("  modelos   : demanda={0} quiebre={1} kmeans={2}" -f $mods.modelos.demanda.tipo, $mods.modelos.quiebre.tipo, $mods.modelos.kmeans.tipo)
$fc = Invoke-RestMethod "$Api/api/v1/forecast?limit=5" -Headers $h -TimeoutSec 20
Write-Host ("  pronostico: {0} filas / primero {1} ({2} unid.)" -f $fc.n, $fc.items[0].nombre, $fc.items[0].pronostico_semana_siguiente)
$seg = Invoke-RestMethod "$Api/api/v1/segments" -Headers $h -TimeoutSec 20
$texto = ($seg.segmentos | ForEach-Object { "$($_.segmento) $($_.pct)%" }) -join ", "
Write-Host ("  segmentos : {0}" -f $texto)
try {
    $sem = Invoke-RestMethod "$Api/api/v1/weeks" -Headers $h -TimeoutSec 20
    Write-Host ("  semanas   : {0} snapshots (ultima {1}, {2} alertas)" -f $sem.n, $sem.semanas[-1].semana, $sem.semanas[-1].alertas)
    $esc = Invoke-RestMethod "$Api/api/v1/scenarios" -Headers $h -TimeoutSec 20
    $lista = ($esc.escenarios | ForEach-Object { "$($_.etiqueta) $($_.mape)%" }) -join " - "
    Write-Host ("  escenarios: {0}" -f $lista)
} catch {
    Write-Host "  ! faltan artefactos de escenarios/semanas" -ForegroundColor Yellow
}

Paso "5. frontend"
Write-Host "  abre la URL del static site y usa 'Obtener codigo de acceso'" -ForegroundColor Green
