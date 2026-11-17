$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz

$scripts = @(
    @{ archivo = "01_dataset.py"; pausa = "Siguiente: la partición 9/2/1" },
    @{ archivo = "02_split.py";   pausa = "Siguiente: ver XGBoost entrenar" },
    @{ archivo = "03_xgboost.py"; pausa = "Siguiente: ver K-Means agrupar" },
    @{ archivo = "04_kmeans.py";  pausa = "Siguiente: las decisiones y el plan" },
    @{ archivo = "05_alertas.py"; pausa = "Siguiente: publicar y abrir el panel" }
)

foreach ($s in $scripts) {
    $ruta = Join-Path $raiz ("demo\" + $s.archivo)
    & python $ruta
    if ($LASTEXITCODE -ne 0) {
        Write-Host "`nEl paso $($s.archivo) falló. Se detiene la demo." -ForegroundColor Red
        exit 1
    }
    Write-Host ""
    Write-Host ("  " + $s.pausa) -ForegroundColor DarkGray
    Read-Host "  Enter para continuar"
}

Write-Host ""
Write-Host "  Último paso (opcional, ~1 min): python demo\06_publicar.py" -ForegroundColor Yellow
Write-Host "  Después abre http://127.0.0.1:8080" -ForegroundColor Gray
