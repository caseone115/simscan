; SimScan - NSIS installer (the local Linux/Wine build path).
;
; The version is NOT written here. It is passed in by the build script:
;
;   makensis -DAPPVERSION=<v> -DVERFOUR=<v.0> -DSRCDIR=... -DOUTDIR=... build/installer.nsi
;
; `build/build_windows.sh` reads the version from `scripts/version.py` (the single
; source, `simscan.__version__`) and passes it in. Hard-coding it here is what let
; the release ship as v1.0.1 carrying an installer that called itself 1.0.0; if
; APPVERSION is missing the build now stops instead.
; `scripts/check_version_consistency.py` asserts this file hard-codes nothing.

!ifndef APPVERSION
  !error "APPVERSION undefined - pass -DAPPVERSION from scripts/version.py"
!endif
!ifndef VERFOUR
  !error "VERFOUR undefined - pass -DVERFOUR from scripts/version.py --four"
!endif
!ifndef APPNAME
  !define APPNAME "SimScan"
!endif
!ifndef SRCDIR
  !define SRCDIR "..\dist\SimScan"
!endif
!ifndef OUTDIR
  !define OUTDIR "..\dist\installer"
!endif

Name "${APPNAME} ${APPVERSION}"
OutFile "${OUTDIR}\${APPNAME}-${APPVERSION}-Setup.exe"
InstallDir "$LOCALAPPDATA\${APPNAME}"
RequestExecutionLevel user
SetCompressor /SOLID lzma

VIProductVersion "${VERFOUR}"
VIAddVersionKey "ProductName"     "${APPNAME}"
VIAddVersionKey "FileDescription" "${APPNAME} Setup"
VIAddVersionKey "FileVersion"     "${VERFOUR}"
VIAddVersionKey "ProductVersion"  "${APPVERSION}"
VIAddVersionKey "CompanyName"     "SimScan"
VIAddVersionKey "LegalCopyright"  "MIT Licence"

!include "MUI2.nsh"
!define MUI_ICON "..\assets\simscan.ico"
!define MUI_UNICON "..\assets\simscan.ico"
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

Section "SimScan" SEC_MAIN
  SetOutPath "$INSTDIR"
  File /r "${SRCDIR}\*.*"
  WriteUninstaller "$INSTDIR\uninstall.exe"
  CreateDirectory "$SMPROGRAMS\${APPNAME}"
  CreateShortCut "$SMPROGRAMS\${APPNAME}\${APPNAME}.lnk" "$INSTDIR\${APPNAME}.exe"
  ; The version the OS reports for this install. A package manager reads this
  ; back to decide whether the installed version matches its manifest, so it has
  ; to be the same version as the filename and the binary's own resource.
  WriteRegStr HKCU "Software\${APPNAME}" "Version" "${APPVERSION}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "DisplayName" "${APPNAME}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "DisplayVersion" "${APPVERSION}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "UninstallString" "$INSTDIR\uninstall.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "Publisher" "SimScan"
SectionEnd

Section "Uninstall"
  Delete "$INSTDIR\uninstall.exe"
  RMDir /r "$INSTDIR"
  Delete "$SMPROGRAMS\${APPNAME}\${APPNAME}.lnk"
  RMDir "$SMPROGRAMS\${APPNAME}"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}"
  DeleteRegKey HKCU "Software\${APPNAME}"
SectionEnd
