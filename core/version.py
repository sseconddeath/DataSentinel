r"""Текущая версия приложения. Единая точка правды для:
- сравнения с GitHub Releases в auto-updater (services/updater.py)
- отображения в Настройках («О приложении»)
- log/diagnostic выводов

При выпуске нового релиза:
1. bump VERSION здесь
2. bump #define MyAppVersion в installer.iss до того же значения
3. `gh release create vX.Y.Z installer_output\Knox_Setup_X.Y.Z.exe ...`
"""
VERSION = "1.0.7"
