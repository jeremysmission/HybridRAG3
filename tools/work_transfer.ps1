$zip = "$env:USERPROFILE\Downloads\session2_transfer.zip"
$tmp = "$env:TEMP\transfer_tmp"
$proj = "C:\Users\randaje\OneDrive - NGC\Desktop\HybridRAG3"
if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
Expand-Archive -Path $zip -DestinationPath $tmp -Force
Copy-Item "$tmp\src\*" -Destination "$proj\src\" -Recurse -Force
Copy-Item "$tmp\tools\*" -Destination "$proj\tools\" -Force
Copy-Item "$tmp\tests\*" -Destination "$proj\tests\" -Force
Copy-Item "$tmp\config\*" -Destination "$proj\config\" -Force
Copy-Item "$tmp\diagnostics\*" -Destination "$proj\diagnostics\" -Force
Copy-Item "$tmp\REDESIGN_README.txt" -Destination "$proj\REDESIGN_README.txt" -Force
Remove-Item $tmp -Recurse -Force
Write-Host "Transfer complete"
