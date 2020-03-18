import win32file, win32con

flags = win32con.FILE_NOTIFY_CHANGE_FILE_NAME
dh = win32file.CreateFile("Z:\\", 0x0001,win32con.FILE_SHARE_READ | win32con.FILE_SHARE_WRITE, None, win32con.OPEN_EXISTING, win32con.FILE_FLAG_BACKUP_SEMANTICS | win32con.FILE_FLAG_OVERLAPPED, None)
while True:
    changes = win32file.ReadDirectoryChangesW(dh, 8192, True, flags)
    for x, file in changes:
        print(x, file)