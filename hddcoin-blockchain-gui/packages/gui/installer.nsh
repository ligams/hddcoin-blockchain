!include "nsDialogs.nsh"

; Add our customizations to the finish page
!macro customFinishPage
XPStyle on

Var DetectDlg
Var FinishDlg
Var HDDcoinSquirrelInstallLocation
Var HDDcoinSquirrelInstallVersion
Var HDDcoinSquirrelUninstaller
Var CheckboxUninstall
Var UninstallHDDcoinSquirrelInstall
Var BackButton
Var NextButton

Page custom detectOldHDDcoinVersion detectOldHDDcoinVersionPageLeave
Page custom finish finishLeave

; Add a page offering to uninstall an older build installed into the hddcoin-blockchain dir
Function detectOldHDDcoinVersion
  ; Check the registry for old hddcoin-blockchain installer keys
  ReadRegStr $HDDcoinSquirrelInstallLocation HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\hddcoin-blockchain" "InstallLocation"
  ReadRegStr $HDDcoinSquirrelInstallVersion HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\hddcoin-blockchain" "DisplayVersion"
  ReadRegStr $HDDcoinSquirrelUninstaller HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\hddcoin-blockchain" "QuietUninstallString"

  StrCpy $UninstallHDDcoinSquirrelInstall ${BST_UNCHECKED} ; Initialize to unchecked so that a silent install skips uninstalling

  ; If registry keys aren't found, skip (Abort) this page and move forward
  ${If} HDDcoinSquirrelInstallVersion == error
  ${OrIf} HDDcoinSquirrelInstallLocation == error
  ${OrIf} $HDDcoinSquirrelUninstaller == error
  ${OrIf} $HDDcoinSquirrelInstallVersion == ""
  ${OrIf} $HDDcoinSquirrelInstallLocation == ""
  ${OrIf} $HDDcoinSquirrelUninstaller == ""
  ${OrIf} ${Silent}
    Abort
  ${EndIf}

  ; Check the uninstall checkbox by default
  StrCpy $UninstallHDDcoinSquirrelInstall ${BST_CHECKED}

  ; Magic create dialog incantation
  nsDialogs::Create 1018
  Pop $DetectDlg

  ${If} $DetectDlg == error
    Abort
  ${EndIf}

  !insertmacro MUI_HEADER_TEXT "Uninstall Old Version" "Would you like to uninstall the old version of HDDcoin Blockchain?"

  ${NSD_CreateLabel} 0 35 100% 12u "Found HDDcoin Blockchain $HDDcoinSquirrelInstallVersion installed in an old location:"
  ${NSD_CreateLabel} 12 57 100% 12u "$HDDcoinSquirrelInstallLocation"

  ${NSD_CreateCheckBox} 12 81 100% 12u "Uninstall HDDcoin Blockchain $HDDcoinSquirrelInstallVersion"
  Pop $CheckboxUninstall
  ${NSD_SetState} $CheckboxUninstall $UninstallHDDcoinSquirrelInstall
  ${NSD_OnClick} $CheckboxUninstall SetUninstall

  nsDialogs::Show

FunctionEnd

Function SetUninstall
  ; Set UninstallHDDcoinSquirrelInstall accordingly
  ${NSD_GetState} $CheckboxUninstall $UninstallHDDcoinSquirrelInstall
FunctionEnd

Function detectOldHDDcoinVersionPageLeave
  ${If} $UninstallHDDcoinSquirrelInstall == 1
    ; This could be improved... Experiments with adding an indeterminate progress bar (PBM_SETMARQUEE)
    ; were unsatisfactory.
    ExecWait $HDDcoinSquirrelUninstaller ; Blocks until complete (doesn't take long though)
  ${EndIf}
FunctionEnd

Function finish

  ; Magic create dialog incantation
  nsDialogs::Create 1018
  Pop $FinishDlg

  ${If} $FinishDlg == error
    Abort
  ${EndIf}

  GetDlgItem $NextButton $HWNDPARENT 1 ; 1 = Next button
  GetDlgItem $BackButton $HWNDPARENT 3 ; 3 = Back button

  ${NSD_CreateLabel} 0 35 100% 12u "HDDcoin has been installed successfully!"
  EnableWindow $BackButton 0 ; Disable the Back button
  SendMessage $NextButton ${WM_SETTEXT} 0 "STR:Let's Farm!" ; Button title is "Close" by default. Update it here.

  nsDialogs::Show

FunctionEnd

; Copied from electron-builder NSIS templates
Function StartApp
  ${if} ${isUpdated}
    StrCpy $1 "--updated"
  ${else}
    StrCpy $1 ""
  ${endif}
  ${StdUtils.ExecShellAsUser} $0 "$launchLink" "open" "$1"
FunctionEnd

Function finishLeave
  ; Launch the app at exit
  Call StartApp
FunctionEnd

; Section
; SectionEnd
!macroend
