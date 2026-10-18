#define MyAppName "NVB AI Studio"
#ifndef MyAppVersion
  #define MyAppVersion "0.1.0"
#endif
#define MyAppPublisher "NVB Tech"
#define MyAppExeName "NVB AI Studio.exe"

[Setup]
AppId={{1D86E14A-76AC-4A39-A1A2-D28E98CD6C04}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\NVB AI Studio
DefaultGroupName=NVB AI Studio
DisableProgramGroupPage=yes
OutputDir=..\installer-output
OutputBaseFilename=NVB-AI-Studio-Setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
PrivilegesRequired=admin
CloseApplications=yes
RestartApplications=no
SetupLogging=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
Source: "..\dist\NVB AI Studio\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\NVB AI Studio"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\NVB AI Studio"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch NVB AI Studio"; Flags: nowait postinstall skipifsilent
