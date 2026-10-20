# wait_for_server.ps1 - Aguarda a porta TCP local estar pronta.
# Parametros:
#   -Url    URL de referencia (padrao: http://localhost:8000/) — a porta e extraida desta URL
#   -MaxTry Numero maximo de tentativas (padrao: 300, a cada 2 s = 600 s no total)
param(
    [string]$Url    = "http://localhost:8000/",
    [int]   $MaxTry = 300,
    [string]$ReadyFile = ""
)

# Extrai a porta da URL para que o script respeite o parametro -Url
$port = 8000
$m = [regex]::Match($Url, ':(\d+)')
if ($m.Success) { $port = [int]$m.Groups[1].Value }

$ok = $false
for ($i = 1; $i -le $MaxTry; $i++) {
    if ($ReadyFile) {
        if (-not (Test-Path -LiteralPath $ReadyFile)) {
            Start-Sleep -Seconds 2
            continue
        }
        try { $readyText = Get-Content -LiteralPath $ReadyFile -Raw -ErrorAction Stop } catch {
            Start-Sleep -Seconds 2
            continue
        }
        if (-not $readyText -or -not $readyText.EndsWith("`n")) {
            Start-Sleep -Seconds 2
            continue
        }
        $Url = $readyText.Trim()
        $readyUri = $null
        if (-not [Uri]::TryCreate($Url, [UriKind]::Absolute, [ref]$readyUri) -or
            $readyUri.Scheme -ne 'http' -or $readyUri.Host -ne '127.0.0.1') {
            Write-Error 'Recibo de abertura invalido.'
            exit 1
        }
        $port = $readyUri.Port
    }
    $tcp = $null
    try {
        $tcp = New-Object System.Net.Sockets.TcpClient
        $tcp.Connect("127.0.0.1", $port)
        $ok = $true
        break
    } catch {
    } finally {
        if ($tcp) { $tcp.Dispose() }
    }
    Write-Host ("    aguardando servidor na porta $port... " + $i + "/" + $MaxTry)
    Start-Sleep -Seconds 2
}

if ($ok) {
    Write-Host ""
    if ($ReadyFile) { Write-Output $Url } else { Write-Host "[OK] Servidor pronto!" }
    exit 0
} else {
    Write-Host ""
    Write-Host "[ERRO] Limite de espera atingido - o servidor nao respondeu a tempo."
    exit 1
}
