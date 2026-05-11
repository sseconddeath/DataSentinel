; DataSentinel — Inno Setup Script
;
; Usage: build.bat does everything automatically, or run manually:
;   1. pyinstaller DataSentinel.spec
;   2. iscc installer.iss

#define MyAppName "DataSentinel"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "DataSentinel"
#define MyAppURL "https://github.com/sseconddeath/DataSentinel"
#define MyAppExeName "DataSentinel.exe"

[Setup]
AppId={{B5E2F8A1-3C4D-4E6F-9A1B-2C3D4E5F6A7B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=installer_output
OutputBaseFilename=DataSentinel_Setup_{#MyAppVersion}
SetupIconFile=icon.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "installollama"; Description: "Установить Ollama (AI-ассистент, ~800 МБ)"; GroupDescription: "Дополнительно:"

[Files]
Source: "dist\DataSentinel\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Удалить {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Запустить DataSentinel"; Flags: nowait postinstall skipifsilent
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -Command ""& {{ Invoke-WebRequest -Uri 'https://ollama.com/download/OllamaSetup.exe' -OutFile '$env:TEMP\OllamaSetup.exe'; Start-Process '$env:TEMP\OllamaSetup.exe' -Wait }}"""; StatusMsg: "Установка Ollama..."; Tasks: installollama; Flags: runhidden waituntilterminated
