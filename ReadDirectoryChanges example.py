import win32file, win32con, win32event, pywintypes

flags = win32con.FILE_NOTIFY_CHANGE_FILE_NAME | win32con.FILE_NOTIFY_CHANGE_LAST_WRITE
dh = win32file.CreateFile("Z:\\", 0x0001,win32con.FILE_SHARE_READ | win32con.FILE_SHARE_WRITE | win32con.FILE_SHARE_DELETE, None, win32con.OPEN_EXISTING, win32con.FILE_FLAG_BACKUP_SEMANTICS | win32con.FILE_FLAG_OVERLAPPED, None)
overlapped = pywintypes.OVERLAPPED()
overlapped.hEvent = win32event.CreateEvent(None, 0, 0, None)
buf = win32file.AllocateReadBuffer(8192)
# changes = []
win32file.ReadDirectoryChangesW(dh, buf, True, flags, overlapped)
while True:
    rc = win32event.MsgWaitForMultipleObjects([overlapped.hEvent], False, 50, win32event.QS_ALLEVENTS)
    if rc == win32event.WAIT_TIMEOUT:
        print('timed out')
    if rc == win32event.WAIT_OBJECT_0:
        nbytes = win32file.GetOverlappedResult(dh, overlapped, True)
        if nbytes:
            bits = win32file.FILE_NOTIFY_INFORMATION(buf, nbytes)
            # changes.extend(bits)
            # print(changes)
            print(bits)
        else:
            print('dir handle closed')


    #attempt 2

# import win32file, win32con, win32api, time

# flags = win32con.FILE_NOTIFY_CHANGE_FILE_NAME | win32con.FILE_NOTIFY_CHANGE_LAST_WRITE
# dh = win32file.CreateFile("C:\\6T Backup\\", 0x0001,win32con.FILE_SHARE_READ | win32con.FILE_SHARE_WRITE, None, win32con.OPEN_EXISTING, win32con.FILE_FLAG_BACKUP_SEMANTICS | win32con.FILE_FLAG_OVERLAPPED, None)
# flags2 = win32con.FILE_NOTIFY_CHANGE_LAST_WRITE

# filelist = {}

# while True:
#     changes = win32file.ReadDirectoryChangesW(dh, 8192, True, flags)
#     for x, file in changes:
#         if x == 1:
#             print('checking file')
#             while True:
#                 time.sleep(.5)
#                 try:
#                     with open("C:\\6T Backup\\"+file, 'r') as test:
#                         print('finally opened!')
#                         break
#                 except:
#                     print("can't open!")
#                     pass


        #attempt 1
# if file in filelist:
#     y = filelist[file]
#     if y == 1 and x == 3:
#         filelist[file] = 3
#     elif y == 3 and x == 3:
#         print("Finished writing",file)
#         filelist.pop(file)
# else:
#     filelist[file] = 1
# print(x, file, time.time())
# print(filelist, x)
        
# changes2 = win32api.FindNextChangeNotification("Z:\\", 0, flags2)
# print(changes2)