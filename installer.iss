; Inno Setup 脚本 —— 生成 Windows 安装包
;
;   "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss
;
; 输入：dist\牙槽骨吸收测量_文件夹版\   （BUILD_MODE=onedir 打出来的）
; 输出：dist\牙槽骨吸收测量_安装包_v<版本>.exe
;
; 为什么安装包用「文件夹版」而不是「单文件版」：
;   单文件 exe 每次启动都要把 70MB 自解压到临时目录，冷启动约 5 秒；
;   安装后的文件夹版直接加载，约 0.5 秒。
;   装一次换来天天快 —— 这正是安装包存在的意义。
;   要发微信/临时用，另有单文件版，不用安装。

#define AppName "牙槽骨吸收测量"
#define AppVer GetEnv('APP_VERSION')
#if AppVer == ""
  #define AppVer "1.0.0"
#endif
#define AppExe "牙槽骨吸收测量_文件夹版.exe"
#define SrcDir "dist\牙槽骨吸收测量_文件夹版"

[Setup]
AppId={{8F3C1A62-4D77-4A5E-9B21-7C0E5A9D3F14}
AppName={#AppName}
AppVersion={#AppVer}
AppVerName={#AppName} {#AppVer}
AppPublisher=牙周研究工具
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; 装到 Program Files 需要管理员权限；用 lowest 会装到用户目录，免管理员。
; 选后者：医院/学校的电脑往往没有管理员权限，能装上比装得"正规"重要。
; PrivilegesRequired=lowest 时 {autopf} 自动指向用户的 Programs 目录。
PrivilegesRequired=lowest
DefaultDirName={autopf}\{#AppName}
OutputDir=dist
OutputBaseFilename={#AppName}_安装包_v{#AppVer}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; 中文界面
ShowLanguageDialog=no
UninstallDisplayName={#AppName}
UninstallDisplayIcon={app}\{#AppExe}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "chinese"; MessagesFile: "compiler:Default.isl"

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
