$key = Read-Host 'Enter Fuyao API key locally' -AsSecureString
$previousProfile = $env:INVESTBUDDY_PROFILE
$previousKey = $env:FUYAO_API_KEY
try {
    if ($key.Length -eq 0) { throw 'Fuyao API key is required.' }
    $env:FUYAO_API_KEY = [Net.NetworkCredential]::new('', $key).Password
    $env:INVESTBUDDY_PROFILE = 'local'
    & (Join-Path $PSScriptRoot '.venv\Scripts\python.exe') -m streamlit run (Join-Path $PSScriptRoot 'app.py') --server.address 127.0.0.1 --server.port 8502
} finally {
    $env:FUYAO_API_KEY = $previousKey
    $env:INVESTBUDDY_PROFILE = $previousProfile
    $key.Dispose()
}
