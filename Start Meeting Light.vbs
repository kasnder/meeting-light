Set fs = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
base = fs.GetParentFolderName(WScript.ScriptFullName)
python = base & "\source\.venv\Scripts\pythonw.exe"
entry = base & "\source\run.py"
If Not fs.FileExists(python) Then
    MsgBox "Run Install.ps1 first to prepare Meeting Light's Python environment.", 48, "Meeting Light"
Else
    sh.Run Chr(34) & python & Chr(34) & " " & Chr(34) & entry & Chr(34), 0, False
End If
