$ErrorActionPreference='Continue'
$profiles = Get-NetFirewallProfile | Select-Object Name,Enabled,DefaultInboundAction
$active = Get-NetConnectionProfile | Select-Object Name,NetworkCategory
$sw = [Diagnostics.Stopwatch]::StartNew()
$rules = Get-NetFirewallRule -Direction Inbound -Enabled True -Action Allow | ForEach-Object { $r=$_; $f=$r | Get-NetFirewallPortFilter; $a=$r | Get-NetFirewallApplicationFilter; [pscustomobject]@{Name=$r.DisplayName;Profile=[string]$r.Profile;Protocol=[string]$f.Protocol;LocalPort=[string]$f.LocalPort;Program=[string]$a.Program} }
$sw.Stop()
"rule count: $($rules.Count)  elapsed: $($sw.Elapsed.TotalSeconds)s"
$json = [pscustomobject]@{Profiles=@($profiles);Active=@($active);Rules=@($rules)} | ConvertTo-Json -Depth 4 -Compress
"json length: $($json.Length)"
