; SimScan - NSIS installer script
;
; Built with the *native* Linux makensis (no Wine needed for this step), so
; it produces a genuine Windows installer without a 32-bit Wine prefix.
;
; Build:  makensis -V2 -DSRCDIR=../dist/SimScan -DOUTDIR=../dist/installer \
;                   build/installer.nsi

Unicode true
!include "MUI2.nsh"
!include "FileFunc.nsh"
!include "LogicLib.nsh"

!define APPNAME     "SimScan"
!define APPVERSION  "1.0.0"
!define PUBLISHER   "SimScan"
!define APPURL      "https://github.com/caseone115/simscan"
!define APPEXE     "SimScan.exe"
!define REGKEY      "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}"

!ifndef SRCDIR
  !define SRCDIR "..\dist\SimScan"
!endif
!ifndef OUTDIR
  !define OUTDIR "..\dist\installer"
!endif

Name "${APPNAME} ${APPVERSION}"
OutFile "${OUTDIR}\${APPNAME}-${APPVERSION}-Setup.exe"
InstallDir "$LOCALAPPDATA\Programs\${APPNAME}"
InstallDirRegKey HKCU "Software\${APPNAME}" "InstallDir"
RequestExecutionLevel user          ; per-user install: no UAC prompt
SetCompressor /SOLID lzma
ShowInstDetails show
ShowUninstDetails show

VIProductVersion "1.0.0.0"
VIAddVersionKey "ProductName"     "${APPNAME}"
VIAddVersionKey "FileDescription" "${APPNAME} Setup"
VIAddVersionKey "FileVersion"     "${APPVERSION}"
VIAddVersionKey "ProductVersion"  "${APPVERSION}"
VIAddVersionKey "LegalCopyright"  "MIT Licence"

!define MUI_ABORTWARNING
!define MUI_ICON   "..\assets\simscan.ico"
!define MUI_UNICON "..\assets\simscan.ico"
!define MUI_HEADERIMAGE
!define MUI_HEADERIMAGE_BITMAP "..\assets\wizard-small.bmp"
!define MUI_WELCOMEFINISHPAGE_BITMAP "..\assets\wizard-large.bmp"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "..\LICENSE"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_RUN "$INSTDIR\${APPEXE}"
!define MUI_FINISHPAGE_RUN_TEXT "Start SimScan now"
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "English"

Section "SimScan (required)" SecMain
  SectionIn RO
  SetOutPath "$INSTDIR"
  File /r "${SRCDIR}\*.*"

  WriteRegStr HKCU "Software\${APPNAME}" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "Software\${APPNAME}" "Version" "${APPVERSION}"

  ; Add/Remove Programs entry so it uninstalls like a normal app
  WriteRegStr   HKCU "${REGKEY}" "DisplayName"     "${APPNAME}"
  WriteRegStr   HKCU "${REGKEY}" "DisplayVersion"  "${APPVERSION}"
  WriteRegStr   HKCU "${REGKEY}" "Publisher"       "${PUBLISHER}"
  WriteRegStr   HKCU "${REGKEY}" "URLInfoAbout"    "${APPURL}"
  WriteRegStr   HKCU "${REGKEY}" "UninstallString" "$\"$INSTDIR\Uninstall.exe$\""
  WriteRegStr   HKCU "${REGKEY}" "QuietUninstallString" "$\"$INSTDIR\Uninstall.exe$\" /S"
  WriteRegStr   HKCU "${REGKEY}" "InstallLocation" "$INSTDIR"
  WriteRegDWORD HKCU "${REGKEY}" "NoModify" 1
  WriteRegDWORD HKCU "${REGKEY}" "NoRepair" 1

  ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
  IntFmt $0 "0x%08X" $0
  WriteRegDWORD HKCU "${REGKEY}" "EstimatedSize" "$0"

  WriteUninstaller "$INSTDIR\Uninstall.exe"
SectionEnd

Section "Start Menu shortcut" SecStartMenu
  CreateDirectory "$SMPROGRAMS\${APPNAME}"
  CreateShortcut "$SMPROGRAMS\${APPNAME}\${APPNAME}.lnk" \
                 "$INSTDIR\${APPEXE}" "" "$INSTDIR\${APPEXE}" 0
  CreateShortcut "$SMPROGRAMS\${APPNAME}\Uninstall ${APPNAME}.lnk" \
                 "$INSTDIR\Uninstall.exe"
SectionEnd

Section /o "Desktop shortcut" SecDesktop
  CreateShortcut "$DESKTOP\${APPNAME}.lnk" \
                 "$INSTDIR\${APPEXE}" "" "$INSTDIR\${APPEXE}" 0
SectionEnd

LangString DESC_SecMain      ${LANG_ENGLISH} "The SimScan application files. Required."
LangString DESC_SecStartMenu ${LANG_ENGLISH} "Add SimScan to the Start Menu."
LangString DESC_SecDesktop   ${LANG_ENGLISH} "Add a SimScan shortcut to the desktop."

!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${SecMain}      $(DESC_SecMain)
  !insertmacro MUI_DESCRIPTION_TEXT ${SecStartMenu} $(DESC_SecStartMenu)
  !insertmacro MUI_DESCRIPTION_TEXT ${SecDesktop}   $(DESC_SecDesktop)
!insertmacro MUI_FUNCTION_DESCRIPTION_END

Section "Uninstall"
  Delete "$DESKTOP\${APPNAME}.lnk"
  RMDir /r "$SMPROGRAMS\${APPNAME}"
  RMDir /r "$INSTDIR"
  DeleteRegKey HKCU "${REGKEY}"
  DeleteRegKey HKCU "Software\${APPNAME}"
SectionEnd
