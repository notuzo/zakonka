#define MyAppName "Законка"
#define MyAppVersion "1.4"
#define MyAppExeName "Zakonka.exe"

[Setup]
AppId={{7E1B5A2C-3D4F-4A8B-9C61-2F0D8E7A5B04}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher=notuzo
VersionInfoVersion=1.4.0.0
VersionInfoProductName={#MyAppName}
VersionInfoDescription={#MyAppName} setup
DefaultDirName={localappdata}\Zakonka
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
CloseApplications=no
OutputDir=installer
OutputBaseFilename=ZakonkaSetup
SetupIconFile=logo.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Ярлыки:"

[Files]
Source: "dist\Zakonka\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Запустить {#MyAppName}"; Flags: nowait postinstall skipifsilent

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
begin
  if CurStep = ssInstall then
    Exec(ExpandConstant('{sys}\taskkill.exe'), '/IM Zakonka.exe /F /T', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;
