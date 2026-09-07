; One unified application. Retain the AI AppId and installation directory for upgrades.
#define AppName "牙槽骨吸收测量"
#define InstallDirName "牙槽骨吸收测量AI"
#define AppVer GetEnv('APP_VERSION')
#if AppVer == ""
  #define AppVer "1.3.0-preview"
#endif
#define AppExe "牙槽骨吸收测量AI.exe"
#define SrcDir "dist\AI-integrated\PanoDentalAI"

[Setup]
AppId={{9D7D2163-EE63-4815-B2C1-37EE3B4E4B50}
AppName={#AppName}
AppVersion={#AppVer}
AppVerName={#AppName} {#AppVer}
AppPublisher=牙周研究工具
DefaultGroupName={#AppName}
UsePreviousGroup=no
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
DefaultDirName={autopf}\{#InstallDirName}
OutputDir=dist\AI-integrated
OutputBaseFilename={#AppName}_安装包_v{#AppVer}
Compression=lzma2/fast
LZMANumBlockThreads=1
LZMADictionarySize=8192
SolidCompression=yes
WizardStyle=modern
ShowLanguageDialog=no
UninstallDisplayName={#AppName}
UninstallDisplayIcon={app}\{#AppExe}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Never terminate a user's running annotation session during an upgrade.
CloseApplications=no
RestartApplications=no

[Languages]
Name: "chinese"; MessagesFile: "packaging\languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建牙槽骨吸收测量桌面快捷方式"; GroupDescription: "附加任务:"; Flags: checkedonce

[Files]
Source: "{#SrcDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; Exact obsolete shortcuts only. Never remove an installation/project directory.
Type: files; Name: "{autodesktop}\牙槽骨吸收测量AI.lnk"
Type: files; Name: "{autodesktop}\牙槽骨吸收测量（分割人工版）.lnk"
Type: files; Name: "{autoprograms}\牙槽骨吸收测量AI\牙槽骨吸收测量AI.lnk"
Type: files; Name: "{autoprograms}\牙槽骨吸收测量AI\牙槽骨吸收测量（分割人工版）.lnk"
Type: files; Name: "{autoprograms}\牙槽骨吸收测量AI\卸载 牙槽骨吸收测量AI.lnk"
Type: dirifempty; Name: "{autoprograms}\牙槽骨吸收测量AI"

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; Comment: "牙齿分割、自动候选与手工标注"
Name: "{group}\卸载 {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; Tasks: desktopicon; Comment: "牙齿分割、自动候选与手工标注"

[Run]
Filename: "{app}\{#AppExe}"; Description: "立即运行 {#AppName}"; Flags: nowait postinstall skipifsilent
