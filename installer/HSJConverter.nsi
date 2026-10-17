Unicode true

!define APP_NAME "画世界Pro 草稿转换器"
!define APP_VERSION "1.0.0"
!define APP_PUBLISHER "HSJ Converter"
!define APP_EXE "HSJConverter.exe"
!define APP_REG "Software\HSJConverter"
!define UNINST_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\HSJConverter"

Name "${APP_NAME}"
Caption "${APP_NAME} ${APP_VERSION} 安装程序"
OutFile "output\HSJConverter-Setup-${APP_VERSION}.exe"
InstallDir "$LOCALAPPDATA\Programs\HSJConverter"
InstallDirRegKey HKCU "${APP_REG}" "InstallDir"
RequestExecutionLevel user
SetCompressor /SOLID lzma
SetCompressorDictSize 64
XPStyle on
ManifestDPIAware true
CRCCheck on
BrandingText "HSJ Converter · 本地离线转换"
ShowInstDetails nevershow
ShowUninstDetails nevershow

VIProductVersion "1.0.0.0"
VIAddVersionKey /LANG=2052 "ProductName" "${APP_NAME}"
VIAddVersionKey /LANG=2052 "FileDescription" "${APP_NAME} 安装程序"
VIAddVersionKey /LANG=2052 "FileVersion" "${APP_VERSION}"
VIAddVersionKey /LANG=2052 "ProductVersion" "${APP_VERSION}"
VIAddVersionKey /LANG=2052 "CompanyName" "${APP_PUBLISHER}"
VIAddVersionKey /LANG=2052 "LegalCopyright" "Copyright © 2026 HSJ Converter"

!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "FileFunc.nsh"

!define MUI_ABORTWARNING
!define MUI_ICON "..\assets\app_icon.ico"
!define MUI_UNICON "..\assets\app_icon.ico"
!define MUI_WELCOMEFINISHPAGE_BITMAP "wizard.bmp"
!define MUI_UNWELCOMEFINISHPAGE_BITMAP "wizard.bmp"
!define MUI_HEADERIMAGE
!define MUI_HEADERIMAGE_BITMAP "header.bmp"
!define MUI_HEADERIMAGE_RIGHT
!define MUI_FINISHPAGE_RUN "$INSTDIR\${APP_EXE}"
!define MUI_FINISHPAGE_RUN_TEXT "立即启动 ${APP_NAME}"
!define MUI_FINISHPAGE_SHOWREADME "$INSTDIR\README.md"
!define MUI_FINISHPAGE_SHOWREADME_TEXT "查看使用说明"
!define MUI_FINISHPAGE_SHOWREADME_NOTCHECKED

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "SimpChinese"

Section "主程序（必需）" SEC_MAIN
  SectionIn RO
  SetShellVarContext current
  SetOutPath "$INSTDIR"
  File /r "..\dist\HSJConverter\*.*"
  WriteUninstaller "$INSTDIR\uninst.exe"

  CreateDirectory "$SMPROGRAMS\${APP_NAME}"
  CreateShortCut "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}"
  CreateShortCut "$SMPROGRAMS\${APP_NAME}\命令行窗口.lnk" "$SYSDIR\cmd.exe" '/k cd /d "$INSTDIR"'
  CreateShortCut "$SMPROGRAMS\${APP_NAME}\卸载 ${APP_NAME}.lnk" "$INSTDIR\uninst.exe"

  WriteRegStr HKCU "${APP_REG}" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "${UNINST_KEY}" "DisplayName" "${APP_NAME}"
  WriteRegStr HKCU "${UNINST_KEY}" "DisplayVersion" "${APP_VERSION}"
  WriteRegStr HKCU "${UNINST_KEY}" "Publisher" "${APP_PUBLISHER}"
  WriteRegStr HKCU "${UNINST_KEY}" "DisplayIcon" "$INSTDIR\${APP_EXE},0"
  WriteRegStr HKCU "${UNINST_KEY}" "UninstallString" '"$INSTDIR\uninst.exe"'
  WriteRegStr HKCU "${UNINST_KEY}" "QuietUninstallString" '"$INSTDIR\uninst.exe" /S'
  WriteRegDWORD HKCU "${UNINST_KEY}" "NoModify" 1
  WriteRegDWORD HKCU "${UNINST_KEY}" "NoRepair" 1
  ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
  IntFmt $0 "0x%08X" $0
  WriteRegDWORD HKCU "${UNINST_KEY}" "EstimatedSize" "$0"
SectionEnd

Section "桌面快捷方式" SEC_DESKTOP
  SetShellVarContext current
  CreateShortCut "$DESKTOP\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}"
SectionEnd

Section /o "关联 .hsj 文件（可选）" SEC_ASSOC
  WriteRegStr HKCU "Software\Classes\.hsj" "" "HSJConverter.Draft"
  WriteRegStr HKCU "Software\Classes\HSJConverter.Draft" "" "画世界Pro 草稿"
  WriteRegStr HKCU "Software\Classes\HSJConverter.Draft\DefaultIcon" "" "$INSTDIR\${APP_EXE},0"
  WriteRegStr HKCU "Software\Classes\HSJConverter.Draft\shell\open\command" "" '"$INSTDIR\${APP_EXE}" "%1"'
  System::Call 'shell32::SHChangeNotify(i 0x08000000, i 0, i 0, i 0)'
SectionEnd

Section "Uninstall"
  SetShellVarContext current
  Delete "$DESKTOP\${APP_NAME}.lnk"
  RMDir /r "$SMPROGRAMS\${APP_NAME}"

  ReadRegStr $0 HKCU "Software\Classes\.hsj" ""
  ${If} $0 == "HSJConverter.Draft"
    DeleteRegKey HKCU "Software\Classes\.hsj"
    DeleteRegKey HKCU "Software\Classes\HSJConverter.Draft"
  ${EndIf}

  DeleteRegKey HKCU "${APP_REG}"
  DeleteRegKey HKCU "${UNINST_KEY}"
  RMDir /r "$INSTDIR"
  System::Call 'shell32::SHChangeNotify(i 0x08000000, i 0, i 0, i 0)'
SectionEnd

Function .onInit
  ${GetParameters} $R0
  ${GetOptions} $R0 "/ASSOC" $R1
  ${IfNot} ${Errors}
    SectionSetFlags ${SEC_ASSOC} ${SF_SELECTED}
  ${EndIf}
FunctionEnd
