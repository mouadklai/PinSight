[Setup]
AppId={{6ab8639b-623a-4f9a-b548-8a39272d09bd}
AppName=PinSight
AppVersion=0.1
AppPublisher=Dr. Mouad Klai
AppPublisherURL=https://mouadklai.github.io/
AppSupportURL=https://mouadklai.github.io/PinSight/
AppUpdatesURL=https://mouadklai.github.io/PinSight/version.json

DefaultDirName={pf}\PinSight
DefaultGroupName=PinSight

OutputDir=installer
OutputBaseFilename=PinSight_v0.1_Setup

Compression=lzma
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64

; ---- Modern look ----
WizardStyle=modern
WizardImageFile=splash_installer.png
WizardSmallImageFile=PinSight.png

; ---- Icons ----
SetupIconFile=PinSight.ico
UninstallDisplayIcon={app}\PinSight_v0.1.exe
UninstallDisplayName=PinSight

DisableProgramGroupPage=no
DisableDirPage=no
DisableReadyMemo=no


[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"


[Messages]
WelcomeLabel1=Welcome to PinSight
WelcomeLabel2=Powerful insights, installed in seconds.


[Files]
Source: "dist\PinSight_v0.1\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs
Source: "PinSight.ico"; DestDir: "{app}"; Flags: ignoreversion


[Tasks]
Name: "desktopicon"; Description: "Create a &desktop icon"; GroupDescription: "Additional icons:"; Flags: unchecked


[Icons]
; Start Menu shortcuts
Name: "{group}\PinSight"; Filename: "{app}\PinSight_v0.1.exe"; IconFilename: "{app}\PinSight.ico"
Name: "{group}\Uninstall PinSight"; Filename: "{uninstallexe}"

; Desktop shortcut (optional)
Name: "{commondesktop}\PinSight"; Filename: "{app}\PinSight_v0.1.exe"; IconFilename: "{app}\PinSight.ico"; Tasks: desktopicon


[Run]
Filename: "{app}\PinSight_v0.1.exe"; Description: "Launch PinSight"; Flags: nowait postinstall skipifsilent
