import win32event, time
timerHandle = win32event.CreateWaitableTimer(None, True, None)
print(time.time())

while True:
    win32event.SetWaitableTimer(timerHandle, -10000000, 0, None, None, True)    # sets of 100 nanoseconds. -10,000,000 = 1 second
    waitForTimer = win32event.WaitForSingleObject(timerHandle, 20000)           # waits for either the timer to trigger, or the 20,000 millisecond (20 second) timeout, whichever comes first.
    if waitForTimer == win32event.WAIT_OBJECT_0:
        print(time.time())
        print("Timer worked!")
    elif waitForTimer == win32event.WAIT_TIMEOUT:
        print("Timer did not trigger before the timeout!")