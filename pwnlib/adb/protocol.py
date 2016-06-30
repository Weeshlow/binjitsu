"""
Implementation of the ADB protocol, as far as Binjitsu needs it.

Documentation is available here:
https://android.googlesource.com/platform/system/core/+/master/adb/protocol.txt
"""
import functools

from ..context import context
from ..util.misc import sh_string
from ..util.packing import p32
from ..tubes.remote import remote

def pack(val):
    return '%04x' % val

def unpack(val):
    return int(val, 16)

OKAY = "OKAY"
FAIL = "FAIL"

class Message(object):
    def __init__(self, string):
        self.string = string
    def __str__(self):
        return ('%04x' % len(self.string)) + self.string
    def __flat__(self):
        return str(self)

class Connection(remote):
    def adb_send(self, message):
        self.send(str(Message(message)))
        return self.recvn(4)
    def unpack(self):
        return unpack(self.recvn(4))

class Host(object):
    def __init__(self):
        self.host = context.adb_host
        self.port = context.adb_port
        self._c   = None

    @property
    def c(self):
        if not self._c:
            self._c = Connection(self.host, self.port)
        return self._c

    def autoclose(fn):
        @functools.wraps(fn)
        def wrapper(self, *a, **kw):
            rv = fn(self, *a, **kw)
            if self._c:
                self._c.close()
                self._c = None
            return rv
        return wrapper

    def with_transport(fn):
        @functools.wraps(fn)
        def wrapper(self, *a, **kw):
            self.transport()
            rv = fn(self, *a, **kw)
            if self._c:
                self._c.close()
                self._c = None
            return rv
        return wrapper

    def send(self, *a, **kw):
        return self.c.adb_send(*a, **kw)

    def unpack(self, *a, **kw):
        return self.c.unpack(*a, **kw)

    def recvl(self):
        length = self.c.unpack()
        return self.c.recvn(length)

    @autoclose
    def kill(self):
        try:
            self.send('host:kill')
        except EOFError:
            pass

    def version(self):
        response = self.send('host:version')
        if response == OKAY:
            return (self.c.unpack(), self.c.unpack())
        log.error("Could not fetch version")

    @autoclose
    def devices(self, long=False):
        msg = 'host:devices'
        if long:
            msg += '-l'
        response = self.send(msg)
        if response == 'OKAY':
            return self.recvl()
        log.error("Could not enumerate devices")

    def transport(self, serial=None):
        msg = 'host:transport:%s' % (serial or context.device)
        if self.send(msg) == FAIL:
            log.error("Could not set transport to %r" % serial)

    @autoclose
    @with_transport
    def execute(self, argv):
        self.transport(context.device)
        if isinstance(argv, str):
            argv = [argv]
        argv = list(map(sh_string, argv))
        cmd = 'exec:%s' % (' '.join(argv))
        if OKAY == self.send(cmd):
            rv = self._c
            self._c = None
            return rv

    @autoclose
    @with_transport
    def remount(self):
        self.send('remount:')
        return self.c.recvall()

    @autoclose
    @with_transport
    def root(self):
        self.send('root:')
        return self.c.recvall()

    @autoclose
    @with_transport
    def unroot(self):
        self.send('unroot:')
        return self.c.recvall()

    @autoclose
    @with_transport
    def disable_verity(self):
        self.send('disable-verity:')
        return self.c.recvall()

    @autoclose
    @with_transport
    def enable_verity(self):
        self.send('enable-verity:')
        return self.c.recvall()

    @autoclose
    @with_transport
    def reconnect(self):
        self.send('reconnect:')
        return self.c.recvall()

    @autoclose
    @with_transport
    def reboot(self):
        self.send('reboot:')
        return self.c.recvall()

    @autoclose
    @with_transport
    def reboot_bootloader(self):
        self.send('reboot:bootloader')
        return self.c.recvall()

    @autoclose
    @with_transport
    def list(self, path):
        if FAIL == self.send('sync:'):
            return

        self.c.flat('LIST', len(path), path, word_size=32)
        files = []
        while True:
            response = self.c.recvn(4)
            if response != 'DENT':
                break

            mode = self.c.u32()
            size = self.c.u32()
            time = self.c.u32()
            name = self.c.recvn(self.c.u32())

            # Ignore the current directory and parent
            if name in ('', '.', '..'):
                continue

            files.append(name)

        return sorted(files)

    @autoclose
    @with_transport
    def write(self, path, mode=0o755):
        if OKAY == self.send('sync:'):
            self.c.flat('SEND', len(path), path + ',' + str(mode))
            self.c.send(path)
            return self.c.recvall()

    @autoclose
    @with_transport
    def read(self, path):
        if OKAY == self.send('sync:'):
            self.c.send('RECV' + p32(len(path)))
            self.c.send(path)
            return self.c.recvall()



"""
import pwnlib.adb.protocol
context.log_level='debug'
while True:
    l = listen(9999).wait_for_connection()
    r = remote('localhost', 5037)
    l <> r

r.flat(pwnlib.adb.protocol.Message('host:version'))
r.recv()


"""
