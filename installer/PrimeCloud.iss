#ifndef AppVersion
  #error AppVersion must be supplied by the release build
#endif

[Setup]
AppId=PrimeCloud
AppName=PrimeCloud
AppVersion={#AppVersion}
AppPublisher=PrimeCloud
AppPublisherURL=https://github.com/L1nuxc/PrimeCloud
DefaultDirName={localappdata}\Programs\PrimeCloud
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
UsePreviousLanguage=no
ShowLanguageDialog=no
DisableDirPage=no
DisableProgramGroupPage=yes
DisableReadyPage=yes
WizardStyle=modern dynamic
CloseApplications=yes
RestartApplications=no
UninstallDisplayIcon={app}\PrimeCloud.exe
OutputDir=..\target\installer
OutputBaseFilename=PrimeCloud-Setup

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:DesktopShortcut}"
Name: "startmenuicon"; Description: "{cm:StartMenuShortcut}"; Flags: unchecked

[CustomMessages]
russian.DesktopShortcut=Создать ярлык на рабочем столе
russian.StartMenuShortcut=Добавить ярлык в меню «Пуск»
russian.OpenPrimeCloud=Открыть PrimeCloud
english.DesktopShortcut=Create a desktop shortcut
english.StartMenuShortcut=Add a shortcut to the Start menu
english.OpenPrimeCloud=Open PrimeCloud

[Files]
Source: "..\target\release\primecloud.exe"; DestDir: "{app}"; DestName: "PrimeCloud.exe"; Flags: ignoreversion

[Icons]
Name: "{userdesktop}\PrimeCloud"; Filename: "{app}\PrimeCloud.exe"; WorkingDir: "{app}"; Tasks: desktopicon
Name: "{userprograms}\PrimeCloud"; Filename: "{app}\PrimeCloud.exe"; WorkingDir: "{app}"; Tasks: startmenuicon

[Run]
Filename: "{app}\PrimeCloud.exe"; Description: "{cm:OpenPrimeCloud}"; WorkingDir: "{app}"; Flags: postinstall nowait skipifsilent
