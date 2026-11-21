Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
currentDir = fso.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = currentDir

userProfile = WshShell.ExpandEnvironmentStrings("%USERPROFILE%")
venvPython = userProfile & "\.venvs\powerbi-validation-tool\Scripts\pythonw.exe"

If fso.FileExists(venvPython) Then
    cmd = """" & venvPython & """ -m app.main"
Else
    cmd = "pythonw -m app.main"
End If

WshShell.Run cmd, 0, False
