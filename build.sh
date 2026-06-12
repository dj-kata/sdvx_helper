#!/usr/bin/env bash
set -euo pipefail
shopt -s nullglob

target="sdvx_helper"
python_candidates=(/mnt/c/*/Python310/python.exe)

ps_quote() {
    local value=${1//\'/\'\'}
    printf "'%s'" "$value"
}

if (( ${#python_candidates[@]} == 0 )); then
    echo "python.exe not found under /mnt/c/*/Python310/" >&2
    exit 1
fi

python="${python_candidates[0]}"
python_win="$(wslpath -w "$python")"
project_dir_win="$(wslpath -w .)"
target_script_win="$(wslpath -w "$target.pyw")"
icon_win="$(wslpath -w icon.ico)"

python_ps="$(ps_quote "$python_win")"
project_dir_ps="$(ps_quote "$project_dir_win")"
target_script_ps="$(ps_quote "$target_script_win")"
icon_ps="$(ps_quote "$icon_win")"
add_data_ps="$(ps_quote "$icon_win;.")"

powershell.exe -NoProfile -Command "Set-Location -LiteralPath $project_dir_ps; \$argsList = @('-m', 'PyInstaller', $target_script_ps, '--clean', '--noconsole', '--onefile', '--icon', $icon_ps, '--add-data', $add_data_ps); & $python_ps @argsList; exit \$LASTEXITCODE"

target_exe="dist/$target.exe"
if [[ ! -f "$target_exe" ]]; then
    echo "$target_exe was not created." >&2
    exit 1
fi

mkdir -p to_bin "$target"
cp -fv "$target_exe" to_bin/
cp -fv "$target_exe" "$target/"
rm -rfv "$target/ocr_reporter.exe"
rm -rfv "$target/manage_score.exe"
rm -rfv "$target"/out/rival*.pkl
cp -a resources to_bin/
cp -a resources "$target/"
rm -rf out/*.xml
rm -rf out/*.pkl
rm -rf out/*.csv
cp -a out to_bin/
cp -a out "$target/"
cp version.txt "$target/"
#zip "$target.zip" "$target"/* "$target"/*/* "$target"/*/*/*
rm -rf "$target.zip"
zip "$target.zip" "$target"/* "$target"/*/*
