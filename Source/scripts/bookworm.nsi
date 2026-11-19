!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "x64.nsh"
Unicode true
CRCCheck on
ManifestSupportedOS all
XPStyle on
Name "$%IAPP_DISPLAY_NAME%"
BrandingText "$%IAPP_DISPLAY_NAME% $%IAPP_VERSION%"
OutFile "$%IAPP_DISPLAY_NAME%-$%IAPP_VERSION%-$%IAPP_ARCH%-setup.exe"
InstallDir "$PROGRAMFILES\Bookworm"
InstallDirRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\$%IAPP_NAME%" "InstallLocation"
RequestExecutionLevel admin
SetCompress auto
SetCompressor /solid lzma
SetDatablockOptimize on
VIAddVersionKey ProductName "$%IAPP_DISPLAY_NAME%"
VIAddVersionKey FileDescription "$%IAPP_DISPLAY_NAME%安装程序"
VIAddVersionKey LegalCopyright "$%IAPP_COPYRIGHT%"
VIAddVersionKey ProductVersion "$%IAPP_VERSION%"
VIAddVersionKey FileVersion "$%IAPP_VERSION%"
VIProductVersion "$%IAPP_VERSION_EX%"
VIFileVersion "$%IAPP_VERSION_EX%"
!define MUI_ICON "builder\assets\$%IAPP_NAME%.ico"
!define MUI_HEADERIMAGE
!define MUI_HEADERIMAGE_BITMAP "builder\assets\$%IAPP_NAME%.bmp"
!define MUI_HEADERIMAGE_BITMAP_NOSTRETCH
!define MUI_WELCOMEFINISHPAGE_BITMAP "builder\assets\$%IAPP_NAME%-logo.bmp"
!define MUI_ABORTWARNING
# Variables to store old version info
Var /GLOBAL OldInstallPath
Var /GLOBAL OldVersionFound
!insertmacro MUI_PAGE_WELCOME
!define MUI_LICENSEPAGE_RADIOBUTTONS
!insertmacro MUI_PAGE_LICENSE "license-zh_CN.txt"
!insertmacro MUI_PAGE_DIRECTORY
var StartMenuFolder
!insertmacro MUI_PAGE_STARTMENU startmenu $StartMenuFolder
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_RUN "$INSTDIR\$%IAPP_NAME%.exe"
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "SimpChinese"
Section
  ${If} $OldVersionFound == 1
    DetailPrint "检测到旧版本，正在卸载……"
        # Kill the old running process if it exists
    IfFileExists "$OldInstallPath\Bookworm.exe" 0 +2
      ExecWait '"$OldInstallPath\Bookworm.exe" kill-other-instances'
          # Set the working directory and execute the old uninstaller
    SetOutPath "$OldInstallPath"
    ExecWait '"$OldInstallPath\Uninstall.exe" /S _?=$OldInstallPath'
    DetailPrint "旧版本已卸载。"
  ${EndIf}
SetShellVarContext All
SetOutPath "$INSTDIR"
File /r "$%IAPP_FROZEN_DIRECTORY%\*"
File /oname=LICENSE.txt "..\LICENSE"
CreateShortCut "$DESKTOP\$%IAPP_DISPLAY_NAME%.lnk" "$INSTDIR\$%IAPP_NAME%.exe" "" "" "" SW_SHOWNORMAL "" "无障碍文档阅读器"
!insertmacro MUI_STARTMENU_WRITE_BEGIN startmenu
CreateDirectory "$SMPROGRAMS\$StartMenuFolder"
CreateShortCut "$SMPROGRAMS\$StartMenuFolder\$%IAPP_DISPLAY_NAME%.lnk" "$INSTDIR\$%IAPP_NAME%.exe"
CreateShortCut "$SMPROGRAMS\$StartMenuFolder\$%IAPP_DISPLAY_NAME% 用户指南.lnk" "$INSTDIR\_internal\resources\userguide\zh_CN\$%IAPP_NAME%.html"
CreateShortCut "$SMPROGRAMS\$StartMenuFolder\卸载$%IAPP_DISPLAY_NAME%.lnk" "$INSTDIR\Uninstall.exe"
!insertmacro MUI_STARTMENU_WRITE_END
WriteUninstaller "$INSTDIR\Uninstall.exe"
WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\$%IAPP_NAME%" "DisplayName" "$%IAPP_DISPLAY_NAME% -  $%IAPP_DESCRIPTION%"
WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\$%IAPP_NAME%" "UninstallString" "$\"$INSTDIR\uninstall.exe$\""
WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\$%IAPP_NAME%" "InstallLocation" $INSTDIR
WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall" "Publisher" "$%IAPP_AUTHOR%"
WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\$%IAPP_NAME%" "DisplayVersion" "$%IAPP_VERSION%"
WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\$%IAPP_NAME%" "Silent Uninstall" "$\"$INSTDIR\uninstall.exe$\" /S"
WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\$%IAPP_NAME%" "DisplayIcon" "$\"$INSTDIR\bookworm.ico$\""
WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\$%IAPP_NAME%" "NoModify" 1
WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\$%IAPP_NAME%" "NoRepair" 1
SectionEnd
Section "Uninstall"
SetShellVarContext All
nsExec::ExecToStack '"$INSTDIR\Bookworm.exe" shell --shell-disintegrate'
DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\$%IAPP_NAME%"
RMDir /r /REBOOTOK $INSTDIR
Delete "$DESKTOP\$%IAPP_DISPLAY_NAME%.lnk"
Delete "$DESKTOP\Bookshelf.lnk"
!insertmacro MUI_STARTMENU_GETFOLDER startmenu $StartMenuFolder
RMDir /r "$SMPROGRAMS\$StartMenuFolder"
SectionEnd

Function .onInit
  StrCpy $LANGUAGE ${LANG_SIMPCHINESE}

  # Set registry view for checking old version and for the new install
  ${If} $%IAPP_ARCH% == "x64"
    SetRegView 64
  ${EndIf}

  # Initialize the flag to '0' (meaning 'not found').
  StrCpy $OldVersionFound 0
    ReadRegStr $OldInstallPath HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\$%IAPP_NAME%" "InstallLocation"
  IfErrors done
  # If ReadRegStr was successful, it means an old version exists. Set the flag to '1' (meaning 'found').
  StrCpy $OldVersionFound 1
done:

  ${If} $OldVersionFound == 1
    StrCpy $instdir "$OldInstallPath"
  ${Else}
    ${If} $%IAPP_ARCH% == "x64"
      StrCpy $instdir "$programfiles64\Bookworm"
    ${Else}
      StrCpy $instdir "$programfiles32\Bookworm"
    ${EndIf}
  ${EndIf}

  IfFileExists "$INSTDIR\Bookworm.exe" 0 +2
    ExecWait '"$INSTDIR\Bookworm.exe" kill-other-instances'
FunctionEnd

Function un.onInit
StrCpy $LANGUAGE ${LANG_SIMPCHINESE}
StrCmp $%IAPP_ARCH% "x64" +1 +2
  SetRegView 64
IfFileExists "$INSTDIR\Bookworm.exe" 0 +2
  ExecWait '"$INSTDIR\Bookworm.exe" kill-other-instances'
FunctionEnd
