import ctypes
import json
import logging
import os
import secrets
import shutil
import socket
import sys
import threading
import time
import urllib.request
from pathlib import Path


def main():
    import webview
    import uvicorn
    from viewer_next.server import create_app
    directory = Path(os.environ.get('LOCALAPPDATA',Path.home()))/'TrainingViewerNext'
    directory.mkdir(parents=True,exist_ok=True)
    logging.basicConfig(filename=directory/'desktop.log',level=logging.INFO,encoding='utf-8')
    kernel = ctypes.windll.kernel32
    kernel.CreateMutexW.restype = ctypes.c_void_p
    mutex = kernel.CreateMutexW(None,False,'Local\\TrainingViewerNextDesktop')
    if kernel.GetLastError()==183:
        handle = ctypes.windll.user32.FindWindowW(None,'Training Viewer')
        if handle:
            ctypes.windll.user32.ShowWindow(handle,9)
            ctypes.windll.user32.SetForegroundWindow(handle)
        return
    token = secrets.token_urlsafe(32)
    server = None
    thread = None
    window = None
    retry = False

    class Bridge:
        def choose_directory(self):
            chosen = window.create_file_dialog(webview.FileDialog.FOLDER)
            return chosen[0] if chosen else None

        def save_writer(self):
            chosen = window.create_file_dialog(webview.FileDialog.SAVE,save_filename='tvlp_writer.py')
            if chosen:
                dest = chosen if isinstance(chosen,str) else chosen[0]
                shutil.copyfile(Path(__file__).with_name('writer.py'),dest)
                return True
            return False

    try:
        sock = socket.socket()
        sock.bind(('127.0.0.1',0))
        port = sock.getsockname()[1]
        app = create_app(directory,token)
        server = uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_config=None,access_log=False))
        thread = threading.Thread(target=lambda:server.run(sockets=[sock]),daemon=True)
        thread.start()
        url = f'http://127.0.0.1:{port}'
        for _ in range(100):
            try:
                request = urllib.request.Request(url+'/api/v2/health',headers={'x-viewer-token':token})
                with urllib.request.urlopen(request,timeout=.3):
                    break
            except OSError:
                if not thread.is_alive():
                    raise RuntimeError('本地服务启动失败')
                time.sleep(.1)
        else:
            raise RuntimeError('本地服务未能及时就绪')
        logging.info('Creating native window')
        window = webview.create_window('Training Viewer',url+'/#token='+token,js_api=Bridge(),width=1280,height=820,min_size=(960,640),background_color='#f6f7f9')
        logging.info('Starting WebView2')
        webview.start(gui='edgechromium')
    except Exception:
        logging.exception('Desktop startup failed')
        result = ctypes.windll.user32.MessageBoxW(None,'启动失败。重试将重新启动应用；取消可导出诊断。','Training Viewer',5|16)
        if result==4:
            retry = True
        else:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk(); root.withdraw()
            dest = filedialog.asksaveasfilename(defaultextension='.log',initialfile='training-viewer-diagnostic.log')
            if dest:
                shutil.copyfile(directory/'desktop.log',dest)
            root.destroy()
    finally:
        if server:
            server.should_exit=True
        if thread:
            thread.join(timeout=10)
        kernel.CloseHandle(ctypes.c_void_p(mutex))
    if retry:
        import subprocess
        command = [sys.executable] if getattr(sys, 'frozen', False) else [sys.executable, str(Path(__file__).resolve().parents[2] / 'desktop_entry.py')]
        subprocess.Popen(command, creationflags=subprocess.CREATE_NO_WINDOW)


if __name__=='__main__':
    main()
