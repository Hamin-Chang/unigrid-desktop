; UNIGRID 윈도우 설치본 (Inno Setup) — §7 6단계 B, 2026-08-19
;
;   ISCC.exe packaging\unigrid.iss
;
; 먼저 packaging\build_win.bat 을 돌려 packaging\dist\UNIGRID\ 를 만들어 둘 것.
; 만드는 것: packaging\dist\UNIGRID-setup-<판>.exe
;
; ⚠️ 서명은 안 한다. 서명 없는 설치본은 SmartScreen 이 "Windows에서 PC를 보호했습니다"
;    를 띄운다 — [추가 정보] → [실행] 으로 넘어갈 수 있다. 고객에게 줄 때 서명을 붙인다.

#define AppName    "UNIGRID"
#define AppVer     GetDateTimeString('yyyymmdd', '', '')
#define AppPub     "중앙대학교 GML"
#define AppExe     "UNIGRID.exe"

[Setup]
AppName={#AppName}
AppVersion={#AppVer}
AppPublisher={#AppPub}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
OutputDir=dist
OutputBaseFilename={#AppName}-setup-{#AppVer}
Compression=lzma2/max
SolidCompression=yes
; 64비트 전용 — 엔진(.ctf)과 MATLAB Runtime 이 64비트다
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; 관리자 권한을 요구하지 않는다 — 사용자 폴더에 깔면 회사 PC 에서도 막히지 않는다
PrivilegesRequiredOverridesAllowed=dialog
DisableProgramGroupPage=yes
WizardStyle=modern
; 경로는 이 .iss 파일이 있는 폴더 기준이다. 그리고 파일 이름은 **영문으로** —
; 지난 윈도우 인계에서 한글 이름이 깨진 적이 있다.
InfoBeforeFile=README_before_install.txt

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[Tasks]
Name: "desktopicon"; Description: "바탕화면에 아이콘 만들기"; GroupDescription: "추가로 할 것:"

[Files]
; 한 폴더 산출물을 통째로 — `_internal\src\app_worker.py` 와 `_internal\engine\` 이
; 반드시 함께 가야 한다(계산이 그 자리를 찾는다).
Source: "dist\UNIGRID\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\{#AppName} 제거"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "지금 UNIGRID 켜기"; Flags: nowait postinstall skipifsilent
