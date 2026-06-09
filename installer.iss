; Inno Setup script для Layout Indicator
; Сборка: ISCC.exe installer.iss  ->  installer\LayoutIndicator-Setup-1.0.exe

#define AppName "Layout Indicator"
#define AppVersion "1.0"
#define AppPublisher "Layout Indicator"
#define ExeName "LayoutIndicator.exe"

[Setup]
AppId={{B6F3E2C1-7A4D-4E2B-9C1A-5D2E8F3A7B10}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
; Установка для текущего пользователя — права администратора не нужны
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DefaultDirName={autopf}\LayoutIndicator
DefaultGroupName=Layout Indicator
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\{#ExeName}
SetupIconFile=icon.ico
OutputDir=installer
OutputBaseFilename=LayoutIndicator-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "autostart"; Description: "Запускать при входе в Windows"; GroupDescription: "Дополнительно:"
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Дополнительно:"; Flags: unchecked
Name: "launchnow"; Description: "Запустить сразу после установки"; GroupDescription: "Дополнительно:"

[Files]
Source: "dist\{#ExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Layout Indicator"; Filename: "{app}\{#ExeName}"
Name: "{group}\Удалить Layout Indicator"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Layout Indicator"; Filename: "{app}\{#ExeName}"; Tasks: desktopicon

[Registry]
; Автозапуск через HKCU\...\Run (удаляется при деинсталляции)
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
    ValueType: string; ValueName: "LayoutIndicator"; \
    ValueData: """{app}\{#ExeName}"""; Tasks: autostart; Flags: uninsdeletevalue

[Run]
Filename: "{app}\{#ExeName}"; Description: "Запустить Layout Indicator"; \
    Flags: nowait postinstall skipifsilent; Tasks: launchnow

[UninstallRun]
; Завершить работающий процесс перед удалением
Filename: "{cmd}"; Parameters: "/C taskkill /F /IM {#ExeName} >nul 2>&1"; \
    Flags: runhidden; RunOnceId: "KillLayoutIndicator"
