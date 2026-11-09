#define AppName "Training Viewer"
[Setup]
AppId=TrainingViewerNext
AppName={#AppName}
AppVersion=2.0.0
DefaultDirName={localappdata}\Programs\TrainingViewerNext
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=TrainingViewerNext-Setup
Compression=lzma2
SolidCompression=yes
UninstallDisplayIcon={app}\TrainingViewer.exe
[Files]
Source: "..\dist\TrainingViewer\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion
Source: "vendor\WebView2.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall; Check: NeedsWebView
[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\TrainingViewer.exe"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\TrainingViewer.exe"
[Run]
Filename: "{app}\TrainingViewer.exe"; Description: "Open Training Viewer"; Flags: postinstall nowait skipifsilent
[Code]
function NeedsWebView: Boolean;
var Version: String;
begin
  Result := not (RegQueryStringValue(HKLM32, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version) and (Version <> '') and (Version <> '0.0.0.0'));
  if Result then
    Result := not (RegQueryStringValue(HKCU, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version) and (Version <> '') and (Version <> '0.0.0.0'));
end;

procedure CurStepChanged(CurStep: TSetupStep);
var ResultCode: Integer;
begin
  if (CurStep = ssPostInstall) and NeedsWebView then begin
    if not Exec(ExpandConstant('{tmp}\WebView2.exe'), '/silent /install', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
      RaiseException('Unable to install WebView2. Please retry installation.');
    if NeedsWebView then
      RaiseException('WebView2 installation did not complete. Please retry installation.');
  end;
end;
