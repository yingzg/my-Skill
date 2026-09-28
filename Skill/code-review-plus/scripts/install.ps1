# install.ps1 — Install code-review-plus as a Claude Code Skill (Windows)
# Run: powershell -ExecutionPolicy Bypass -File scripts\install.ps1

$ErrorActionPreference = "Stop"

$SKILL_NAME = "code-review-plus"
$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$SOURCE_DIR = Split-Path -Parent $SCRIPT_DIR
$TARGET_DIR = Join-Path $env:USERPROFILE ".claude\skills\$SKILL_NAME"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  CodeReviewPlus Skill Installer" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Source: $SOURCE_DIR" -ForegroundColor Blue
Write-Host "Target: $TARGET_DIR" -ForegroundColor Blue
Write-Host ""

# --- Detect AI CLI tools ---
Write-Host "Detecting AI CLI tools..." -ForegroundColor Yellow

$tools = @("codex")
$available = @()
foreach ($t in $tools) {
    if (Get-Command $t -ErrorAction SilentlyContinue) {
        $ver = try { & $t --version 2>$null | Select-Object -First 1 } catch { "installed" }
        Write-Host "   + $t - $ver" -ForegroundColor Green
        $available += $t
    } else {
        Write-Host "   - $t - not found" -ForegroundColor Red
    }
}

Write-Host ""
if ($available.Count -eq 0) {
    Write-Host "Warning: Codex CLI not detected." -ForegroundColor Yellow
    Write-Host "The skill will still install, but code review requires Codex:" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  npm install -g @openai/codex" -ForegroundColor Cyan
    Write-Host ""
} else {
    Write-Host "Found $($available.Count) tool(s)" -ForegroundColor Green
}

# --- Check source files ---
$skillMd = Join-Path $SOURCE_DIR "SKILL.md"
if (-not (Test-Path $skillMd)) {
    Write-Host "Error: SKILL.md not found in $SOURCE_DIR" -ForegroundColor Red
    Write-Host "Please run from the extracted zip directory." -ForegroundColor Red
    exit 1
}

# --- Install to ~/.claude/skills/ ---
Write-Host "Installing skill..." -ForegroundColor Yellow

if (Test-Path $TARGET_DIR) {
    Write-Host "Existing installation found, updating..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force $TARGET_DIR
}

$scriptsTarget = Join-Path $TARGET_DIR "scripts"
New-Item -ItemType Directory -Path $scriptsTarget -Force | Out-Null

# Copy SKILL.md
Copy-Item $skillMd -Destination $TARGET_DIR

# Copy scripts
$scriptFiles = @("cross-review.sh", "review-runner.sh", "live-review.sh")
foreach ($script in $scriptFiles) {
    $src = Join-Path $SOURCE_DIR "scripts\$script"
    if (Test-Path $src) {
        Copy-Item $src -Destination $scriptsTarget
    }
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  Installation complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Installed to: $TARGET_DIR" -ForegroundColor Blue
Write-Host ""
Write-Host "Usage:"
Write-Host '  1. Start a new Claude Code conversation (or restart current one)'
Write-Host '  2. The skill will be auto-detected'
Write-Host '  3. Say "code review" or "/code-review-plus" to invoke'
Write-Host ""
