Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = "C:\Users\25713\Desktop\web-fast"
sh.Run "pythonw webfast.py app", 0, False
