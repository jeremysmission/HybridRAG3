$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$dest = 'D:\HybridRAG3\.tmp_online_bank'
if (Test-Path $dest) { Remove-Item -Recurse -Force $dest }
New-Item -ItemType Directory -Path $dest | Out-Null

$items = @(
    @{ name='w3_dummy.pdf'; url='https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf' },
    @{ name='w3_rfc2616.txt'; url='https://www.w3.org/Protocols/rfc2616/rfc2616.txt' },
    @{ name='opencv_sudoku.png'; url='https://raw.githubusercontent.com/opencv/opencv/master/samples/data/sudoku.png' },
    @{ name='pillow_hopper.jpg'; url='https://raw.githubusercontent.com/python-pillow/Pillow/main/Tests/images/hopper.jpg' },
    @{ name='wireshark_readme.md'; url='https://raw.githubusercontent.com/wireshark/wireshark/master/README.md' },
    @{ name='sample_dhcp.pcapng'; url='https://wiki.wireshark.org/uploads/__moin_import__/attachments/SampleCaptures/dhcp.pcapng' },
    @{ name='sample_dns_port.pcap'; url='https://wiki.wireshark.org/uploads/__moin_import__/attachments/SampleCaptures/dns_port.pcap' },
    @{ name='sample_http_gzip.cap'; url='https://wiki.wireshark.org/uploads/__moin_import__/attachments/SampleCaptures/http_gzip.cap' },
    @{ name='ezdxf_sample.dxf'; url='https://raw.githubusercontent.com/mozman/ezdxf/master/examples_dxf/3dface.dxf' },
    @{ name='sample_mbox.mbox'; url='https://raw.githubusercontent.com/qsnake/git/master/t/t5100/sample.mbox' },
    @{ name='scan_like.tif'; url='https://raw.githubusercontent.com/tesseract-ocr/tesseract/main/test/testing/phototest.tif' },
    @{ name='scan_like_rotated.png'; url='https://raw.githubusercontent.com/tesseract-ocr/tessdoc/main/images/OSD.png' },
    @{ name='mail_like.eml'; url='https://raw.githubusercontent.com/robertklep/node-mbox/master/test/fixtures/fixtures.mbox' }
)

$log = @()
foreach ($it in $items) {
    $out = Join-Path $dest $it.name
    try {
        Invoke-WebRequest -UseBasicParsing -Uri $it.url -OutFile $out -TimeoutSec 60
        $size = (Get-Item $out).Length
        $log += [pscustomobject]@{name=$it.name; url=$it.url; ok=$true; size=$size; error=''}
        Write-Output ("OK   {0}  ({1} bytes)" -f $it.name, $size)
    } catch {
        if (Test-Path $out) { Remove-Item -Force $out -ErrorAction SilentlyContinue }
        $msg = $_.Exception.Message
        $log += [pscustomobject]@{name=$it.name; url=$it.url; ok=$false; size=0; error=$msg}
        Write-Output ("FAIL {0}  ({1})" -f $it.name, $msg)
    }
}

$log | ConvertTo-Json -Depth 4 | Set-Content -Path (Join-Path $dest 'download_log.json') -Encoding UTF8
$okCount = ($log | Where-Object { $_.ok }).Count
$failCount = ($log | Where-Object { -not $_.ok }).Count
Write-Output ("SUMMARY ok={0} fail={1} dest={2}" -f $okCount, $failCount, $dest)
