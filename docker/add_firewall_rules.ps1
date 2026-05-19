# AoT-AI Docker 방화벽 규칙 추가 스크립트
# 관리자 권한으로 실행하세요: 마우스 우클릭 → "관리자 권한으로 실행"

$rules = @(
    @{ Name = "AoT-AI Web UI (8084)";   Port = 8084 },
    @{ Name = "AoT-AI MQTT (1883)";     Port = 1883 },
    @{ Name = "AoT-AI InfluxDB (8087)"; Port = 8087 },
    @{ Name = "AoT-AI MQTT WS (9001)";  Port = 9001 }
)

foreach ($r in $rules) {
    $existing = Get-NetFirewallRule -DisplayName $r.Name -ErrorAction SilentlyContinue
    if ($existing) {
        Write-Host "[SKIP] 이미 존재: $($r.Name)"
    } else {
        New-NetFirewallRule `
            -DisplayName $r.Name `
            -Direction Inbound `
            -Action Allow `
            -Protocol TCP `
            -LocalPort $r.Port `
            -Profile Any | Out-Null
        Write-Host "[OK]   추가됨: $($r.Name) (TCP $($r.Port))"
    }
}

Write-Host ""
Write-Host "=== 현재 AoT 방화벽 규칙 ==="
Get-NetFirewallRule | Where-Object { $_.DisplayName -like 'AoT-AI*' } |
    Select-Object DisplayName, Enabled | Format-Table -AutoSize
