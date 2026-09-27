; SimScan - Inno Setup script
; Produces a single SimScanSetup.exe that installs the app with a normal
; Windows wizard (Next > Next > Finish), a Start Menu entry and an
; uninstaller.
;
; Build:  iscc build/simscan.iss   (after PyInstaller has produced dist\SimScan)

#define AppName        "SimScan"
#define AppVersion     "1.0.0"
#define AppPublisher   "SimScan"
#define AppURL         "https://github.com/caseone115/simscan"
#define AppExeName     "SimScan.exe"

[Setup]
AppId={{8F3B2C41-7D5E-4A19-9C6B-5E21A7D4F8C3}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
LicenseFile=..\LICENSE
OutputDir=..\dist\installer
OutputBaseFilename=SimScan-{#AppVersion}-Setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName}
; unsigned build: SmartScreen will show "More info > Run anyway"
SetupIconFile=..\assets\simscan.ico
WizardSmallImageFile=..\assets\wizard-small.bmp
WizardImageFile=..\assets\wizard-large.bmp

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; \
    GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "quicklaunchicon"; Description: "{cm:CreateQuickLaunchIcon}"; \
    GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked; \
    OnlyBelowVersion: 6.1; Components: not (Tasks: desktopicon)

[Files]
Source: "..\dist\SimScan\*"; DestDir: "{app}"; \
    Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}";              Filename: "{app}\{#AppExeName}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}";        Filename: "{app}\{#AppExeName}"; \
    Tasks: desktopicon
Name: "{userappdata}\Microsoft\Internet Explorer\Quick Launch\{#AppName}"; \
    Filename: "{app}\{#AppExeName}"; Tasks: quicklaunchicon

[Run]
Filename: "{app}\{#AppExeName}"; \
    Description: "{cm:LaunchProgram,{#StringChange(AppName, '&', '&&')}}"; \
    Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\_internal"
