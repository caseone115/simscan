; SimScan - Inno Setup script.  This is the installer CI builds and ships.
;
; The version is NOT written here. CI reads it from scripts/version.py (the
; single source, simscan/__init__.py:__version__) and passes it in:
;
;     ISCC.exe /DAppVersion=1.0.1 /DVerFour=1.0.1.0 build\simscan.iss
;
; If it is not passed, the build stops rather than falling back to a stale
; number. That fallback is exactly how the v1.0.1 release came to ship
; SimScan-1.0.0-Setup.exe with an internal version of 1.0.0 and an uninstall
; entry writing DisplayVersion 1.0.0. A winget manifest asserts a version and
; then checks the version the installer actually installed, so this drift was
; the first thing a moderator would have rejected.
;
; build/simscan.iss, CI and scripts/check_version_consistency.py all agree that
; this file must contain no version literal of its own.

#if !defined(AppVersion)
  #error AppVersion is not defined. Pass /DAppVersion=<scripts/version.py>
#endif
#if !defined(VerFour)
  #error VerFour is not defined. Pass /DVerFour=<scripts/version.py --four>
#endif

#define AppName        "SimScan"
#define AppPublisher   "SimScan"
#define AppURL         "https://github.com/caseone115/simscan"
#define AppExeName     "SimScan.exe"

[Setup]
; All relative paths below resolve from this file's own directory (build/),
; which is how ISCC works - do not add SourceDir, it changes that base.
AppId={{8F3B2C41-7D5E-4A19-9C6B-5E21A7D4F8C3}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}
; The version Windows reports for the installer itself, and the product version
; it writes into Add/Remove Programs. Both must equal the version above - this
; is the assertion a package manager reads back.
VersionInfoVersion={#VerFour}
VersionInfoProductVersion={#AppVersion}
VersionInfoProductName={#AppName}
VersionInfoCompany={#AppPublisher}
VersionInfoDescription={#AppName} Setup
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

[Files]
Source: "..\dist\SimScan\*"; DestDir: "{app}"; \
    Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}";              Filename: "{app}\{#AppExeName}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}";        Filename: "{app}\{#AppExeName}"; \
    Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; \
    Description: "{cm:LaunchProgram,{#StringChange(AppName, '&', '&&')}}"; \
    Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\_internal"
