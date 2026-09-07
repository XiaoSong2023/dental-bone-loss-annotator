; One shared installation, two explicit annotation modes. Original manual 1.0 stays intact.
#define AppName "牙槽骨吸收测量AI"
#define ManualName "牙槽骨吸收测量（分割人工版）"
#define AppVer GetEnv('APP_VERSION')
#if AppVer == ""
  #define AppVer "1.2.0-preview"
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
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
DefaultDirName={autopf}\{#AppName}
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
Name: "desktopicon"; Description: "创建自动候选版与分割人工版两个桌面快捷方式"; GroupDescription: "附加任务:"; Flags: checkedonce

[Files]
Source: "{#SrcDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"; Parameters: "--annotation-mode full"; WorkingDir: "{app}"; Comment: "自动分割与三点候选，人工复核"
Name: "{group}\{#ManualName}"; Filename: "{app}\{#AppExe}"; Parameters: "--annotation-mode manual"; WorkingDir: "{app}"; Comment: "仅自动分割，人工标注四点"
Name: "{group}\卸载 {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Parameters: "--annotation-mode full"; WorkingDir: "{app}"; Tasks: desktopicon; Comment: "自动分割与三点候选，人工复核"
Name: "{autodesktop}\{#ManualName}"; Filename: "{app}\{#AppExe}"; Parameters: "--annotation-mode manual"; WorkingDir: "{app}"; Tasks: desktopicon; Comment: "仅自动分割，人工标注四点"

[Run]
Filename: "{app}\{#AppExe}"; Parameters: "--annotation-mode manual"; Description: "立即运行 {#ManualName}"; Flags: nowait postinstall skipifsilent
