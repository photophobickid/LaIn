@echo off
REM Остановить только индикатор раскладки (по командной строке процесса)
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and $_.CommandLine -like '*layout_indicator.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
echo Индикатор остановлен (если был запущен).
