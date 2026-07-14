' 콘솔 창 없이 백그라운드로 감시 시작 (더블클릭 실행)
Set shell = CreateObject("WScript.Shell")
shell.CurrentDirectory = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
shell.Run "cmd /c set PYTHONIOENCODING=utf-8 && pythonw watch.py", 0, False
