; Isolated AI preview installation: keeps the user's existing manual app intact.
#define AppName "牙槽骨吸收测量AI"
#define AppVer GetEnv('APP_VERSION')
#if AppVer == ""
  #define AppVer "1.1.0-ai-preview"
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
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "chinese"; MessagesFile: "packaging\languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务:"; Flags: checkedonce

[Files]
Source: "{#SrcDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\卸载 {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "立即运行 {#AppName}"; Flags: nowait postinstall skipifsilent
