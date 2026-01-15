#!/usr/bin/env pwsh
# Restart the application's PostgreSQL database container

Write-Host "Checking for existing kofc-postgres container..."
$existing = docker ps -a --format "{{.Names}}" | Select-String "kofc-postgres"

if ($existing) {
    Write-Host "Found existing kofc-postgres container, removing it..."
    docker stop kofc-postgres 2>$null
    docker rm kofc-postgres 2>$null
}

Write-Host "Starting kofc-postgres container..."
docker run `
    --name kofc-postgres `
    -e POSTGRES_PASSWORD=dev123 `
    -e POSTGRES_DB=kofc_accounting `
    -p 5432:5432 `
    -d postgres:15-alpine

Write-Host "Waiting for database to be ready..."
Start-Sleep -Seconds 3

Write-Host "Checking database connection..."
$counter = 0
while ($counter -lt 10) {
    try {
        docker exec kofc-postgres pg_isready -U postgres | Out-Null
        if ($?) {
            Write-Host "✓ Database is ready!"
            break
        }
    } catch {
        # Silently retry
    }
    $counter++
    if ($counter -lt 10) {
        Start-Sleep -Seconds 1
    }
}

if ($counter -eq 10) {
    Write-Host "✗ Database did not start in time"
    exit 1
}

Write-Host "`nApplication database (kofc-postgres) is ready!"
Write-Host "Connection: postgresql://postgres:dev123@localhost:5432/kofc_accounting"
