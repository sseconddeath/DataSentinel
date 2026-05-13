; Knox — Inno Setup Script
;
; Usage: build.bat does everything automatically, or run manually:
;   1. pyinstaller Knox.spec
;   2. iscc installer.iss

#define MyAppName "Knox"
#define MyAppVersion "1.0.6"
#define MyAppPublisher "Knox"
#define MyAppURL "https://github.com/sseconddeath/Knox"
#define MyAppExeName "Knox.exe"

[Setup]
AppId={{47EFED1F-8824-425D-8455-A57442E237A4}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=installer_output
OutputBaseFilename=Knox_Setup_{#MyAppVersion}
SetupIconFile=icon.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
; Auto-updater запускает инсталлятор пока Knox.exe ещё работает —
; force-закрываем его, иначе Inno не сможет переписать файлы.
CloseApplications=force
CloseApplicationsFilter=*.exe,*.dll,*.pyd

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "installollama"; Description: "Установить Ollama (AI-ассистент, ~800 МБ)"; GroupDescription: "Дополнительно:"

[Files]
Source: "dist\Knox\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Удалить {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
; Без skipifsilent — auto-updater запускает инсталлятор в /SILENT,
; и нам нужно чтобы он перезапустил Knox.exe после обновления.
Filename: "{app}\{#MyAppExeName}"; Description: "Запустить Knox"; Flags: nowait postinstall
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -Command ""& {{ Invoke-WebRequest -Uri 'https://ollama.com/download/OllamaSetup.exe' -OutFile '$env:TEMP\OllamaSetup.exe'; Start-Process '$env:TEMP\OllamaSetup.exe' -ArgumentList '/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART' -Wait }}"""; StatusMsg: "Скачиваю и устанавливаю Ollama (~800 МБ, несколько минут)..."; Tasks: installollama; Flags: runhidden waituntilterminated
