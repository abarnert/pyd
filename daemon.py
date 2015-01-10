#!/usr/bin/env python3

import contextlib
import os
import select
import socket
import sys
import threading

@contextlib.contextmanager
def unlinking(path):
    try:
        yield path
    finally:
        os.unlink(path)

@contextlib.contextmanager
def exiting(retcode=0):
    try:
        yield
    finally:
        os._exit(retcode)

@contextlib.contextmanager
def backgrounding(target):
    t = threading.Thread(target=target)
    t.start()
    try:
        yield t
    finally:
        t.join()
        
class Daemon(object):
    def __init__(self, path):
        self.path = path
    def kill(self):
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.connect(self.path)
            sock.close()
            return True
        except FileNotFoundError:
            return False
    def connect(self):
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.connect(self.path)
        except FileNotFoundError:
            pid = self.start()
            print('Started daemon on {}'.format(pid))
            sock.connect(self.path)
        return sock
    def execute(self, cmd, datafile=None):
        with self.connect() as sock:
            with sock.makefile('r') as r:
                sock.sendall(cmd.encode('utf-8') + b'\n')
                pr, pw = os.pipe()
                def writer():
                    if not datafile:
                        return
                    try:
                        while True:
                            read = datafile.read
                            if getattr(datafile, 'line_buffering', False):
                                read = datafile.readline
                            # Note that this depends on datafile being
                            # something very much like sys.stdin in normal
                            # line-buffered mode on Linux, Mac, and *BSD.
                            r, _, _ = select.select([datafile, pr], [], [])
                            if datafile in r:
                                buf = read()
                                if not buf:
                                    sock.shutdown(socket.SHUT_WR)
                                    return
                                sock.sendall(buf.encode('utf-8'))
                            if pr in r:
                                return
                    except BrokenPipeError:
                        pass
                with backgrounding(writer):
                    for line in r:
                        yield line
                    os.write(pw, b'0')
    def initialize(self):
        pass
    def handle(self, cmd, rfile, wfile):
        wfile.write('Ignoring command {}\n'.format(cmd))
        for line in rfile:
            wfile.write('Ignoring input {}'.format(line))
    def start(self):
        ssock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        ssock.bind(self.path)
        ssock.listen(1)
        pid = os.fork()
        if pid:
            ssock.close()
            return pid
        with exiting(0), ssock, unlinking(self.path):
            os.setsid()
            #sys.stdin.close()
            #sys.stdout.close()
            #sys.stderr.close()
            self.initialize()
            while True:
                csock, addr = ssock.accept()
                with csock, csock.makefile('r') as r, csock.makefile('w') as w:
                    cmd = r.readline()
                    if not cmd:
                        return
                    self.handle(cmd, r, w)

