; اسکریپت Inno Setup برای ساخت فایل نصب ویندوز.
; اجرا:  ISCC.exe /DMyAppVersion=1.0.0 installer\PromptVault.iss
; پیش‌نیاز: ابتدا pyinstaller --noconfirm --clean PromptVault.spec  (خروجی در dist\PromptVault)

#ifndef MyAppVersion
  #define MyAppVersion "1.0.0"
#endif
#define MyAppName "PromptVault"
#define MyAppExe "PromptVault.exe"

[Setup]
AppId={{6F1C7E0E-5A53-4D6C-9A4E-0F6F2F5D7A11}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=Mohammadtaha Taherian
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=Output
OutputBaseFilename=PromptVault-Setup-{#MyAppVersion}
SetupIconFile=..\app\assets\icon.ico
UninstallDisplayIcon={app}\{#MyAppExe}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\PromptVault\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

; نکته: اطلاعات کاربر در %LOCALAPPDATA%\PromptVault است و هنگام حذف برنامه پاک نمی‌شود (عمداً).
