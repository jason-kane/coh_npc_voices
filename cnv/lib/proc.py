import logging
import time

import pyautogui as keyboard
import win32api
import win32con
import win32process
from win32gui import GetForegroundWindow, GetWindowText
import pywintypes

log = logging.getLogger(__name__)


def coh_is_foreground(warn=None):
    # only send keyboard activity to the city of heroes window
    # if it is not the foreground window do not do anything.
    foreground_window_handle = GetForegroundWindow()
    pid = win32process.GetWindowThreadProcessId(foreground_window_handle)

    try:
        handle = win32api.OpenProcess(win32con.PROCESS_QUERY_INFORMATION | win32con.PROCESS_VM_READ, False, pid[1])
    except pywintypes.error as err:
        log.warning(err)
        return False
    
    proc_name = win32process.GetModuleFileNameEx(handle, 0)
    zone = GetWindowText(foreground_window_handle)
    if warn:
        log.warning(warn)
    else:
        log.info(f'{zone=}')

    return proc_name.split("\\")[-1] == "cityofheroes.exe"


def send_chatstring(message):
    if not coh_is_foreground():
        log.error('cityofheroes.exe is not the foreground process')
        return
    
    # bring the chat to foreground
    keyboard.press("enter")
    # disable user input?
    keyboard.typewrite(message)


def send_log_lock(timeout=10):
    # this will block until coh is the foreground
    start = int(time.time())
    success = False
    while not success:
        success = coh_is_foreground(
            warn="Waiting for City of Heroes to be the foreground process... (timeout in %s)" % (
                int((start + timeout) - time.time())
            )
        ) 

        if not success:
            if time.time() > (start + timeout):
                log.warning('Timeout exceeded.  Not locked to city of heroes.  Some features unavailable.')
                return
            else:
                time.sleep(1)
    
    # send to a tell to ourselves with an infodump
    #for var in ['name', 'level', 'primary', 'secondary', 'archetype']:
    send_chatstring('/tell $name, [SIDEKICK] name="$name";level="$level"\n')    
    send_chatstring('/tell $name, [SIDEKICK] primary="$primary";secondary="$secondary"\n');
    send_chatstring('/tell $name, [SIDEKICK] archetype="$archetype"\n')
    
