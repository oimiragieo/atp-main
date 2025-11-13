# PowerShell script to download and install protoc
param(
    [string]$ProtocVersion = "25.1",
    [string]$DownloadUrl = "https://github.com/protocolbuffers/protobuf/releases/download/v$ProtocVersion/protoc-$ProtocVersion-win64.zip",
    [string]$ZipFile = "protoc.zip",
    [string]$ExtractPath = "$env:TEMP\protoc"
)

Write-Host "Downloading protoc $ProtocVersion..." -ForegroundColor Green

try {
    # Download the zip file
    Invoke-WebRequest -Uri $DownloadUrl -OutFile $ZipFile -UseBasicParsing

    Write-Host "Extracting protoc..." -ForegroundColor Green

    # Extract the zip file
    if (Test-Path $ExtractPath) {
        Remove-Item $ExtractPath -Recurse -Force
    }
    New-Item -ItemType Directory -Path $ExtractPath -Force | Out-Null
    Expand-Archive -Path $ZipFile -DestinationPath $ExtractPath -Force

    # Find protoc.exe
    $protocPath = Get-ChildItem -Path $ExtractPath -Recurse -Filter "protoc.exe" | Select-Object -First 1

    if ($protocPath) {
        $protocDir = Split-Path $protocPath.FullName
        Write-Host "protoc found at: $($protocPath.FullName)" -ForegroundColor Green

        # Add to PATH for current session
        $env:PATH = "$protocDir;$env:PATH"

        # Test protoc
        & $protocPath.FullName --version

        Write-Host "protoc installed successfully!" -ForegroundColor Green
        Write-Host "PATH updated for current session." -ForegroundColor Yellow
    } else {
        Write-Error "protoc.exe not found in extracted files"
        exit 1
    }
} catch {
    Write-Error "Failed to download/install protoc: $_"
    exit 1
}
