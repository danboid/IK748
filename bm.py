import socket, struct, time

class BM:
    def __init__(self, host='127.0.0.1', port=6502):
        self.s = socket.create_connection((host, port))
        self.rid = 1
        self.banks = None

    def _recv(self, n):
        b = b''
        while len(b) < n:
            c = self.s.recv(n - len(b))
            if not c:
                raise EOFError
            b += c
        return b

    def cmd(self, ctype, body=b''):
        rid = self.rid; self.rid += 1
        self.s.sendall(struct.pack('<BBIIB', 2, 2, len(body), rid, ctype) + body)
        while True:
            hdr = self._recv(12)
            _, _, ln, rtype, err, r = struct.unpack('<BBIBBI', hdr)
            data = self._recv(ln)
            if r == rid:
                if err:
                    raise RuntimeError('monitor error %02x for cmd %02x' % (err, ctype))
                return rtype, data

    def bank_id(self, name):
        if self.banks is None:
            _, d = self.cmd(0x82)
            n = struct.unpack('<H', d[:2])[0]; p = 2; self.banks = {}
            for _ in range(n):
                isz = d[p]; bid = struct.unpack('<H', d[p+1:p+3])[0]
                nl = d[p+3]; nm = d[p+4:p+4+nl].decode(); self.banks[nm] = bid
                p += 1 + isz
        return self.banks[name]

    def mem(self, start, end, bank='cpu'):
        body = struct.pack('<BHHBH', 0, start, end, 0, self.bank_id(bank))
        _, d = self.cmd(0x01, body)
        return d[2:]

    def resume(self):
        self.cmd(0xaa)

    def keys(self, text):
        t = text.encode('latin1')
        self.cmd(0x72, bytes([len(t)]) + t)

    def joy(self, port, value):
        # value: active-high bits up=1 down=2 left=4 right=8 fire=16
        self.cmd(0xa2, struct.pack('<HH', port, value))

    def display(self):
        _, d = self.cmd(0x84, bytes([1, 0]))
        fl, dw, dh, ow, oh, iw, ih, bpp = struct.unpack('<IHHHHHHB', d[:17])
        blen = struct.unpack('<I', d[17:21])[0]
        b=d[21:]; b=b+bytes(dw*dh-len(b)); return dw, dh, ow, oh, iw, ih, b

    def wait_event(self, want=0x62, timeout=5):
        self.s.settimeout(timeout)
        try:
            while True:
                hdr = self._recv(12)
                _, _, ln, rtype, err, r = struct.unpack('<BBIBBI', hdr)
                data = self._recv(ln)
                if rtype == want:
                    return data
        finally:
            self.s.settimeout(None)

    def cp_set(self, start, end, op=4):
        _, d = self.cmd(0x12, struct.pack('<HHBBBB', start, end, 1, 1, op, 0))
        return struct.unpack('<I', d[:4])[0]

    def cp_del(self, n):
        self.cmd(0x13, struct.pack('<I', n))

    def step(self, n=1):
        self.cmd(0x71, struct.pack('<BH', 0, n))
        self.wait_event(0x62)

    def regs(self):
        _, d = self.cmd(0x31, bytes([0]))
        n = struct.unpack('<H', d[:2])[0]; p = 2; out = {}
        for _ in range(n):
            sz = d[p]; rid = d[p+1]; val = struct.unpack('<H', d[p+2:p+4])[0]
            out[rid] = val; p += 1 + sz
        return out

    def poke(self, start, data, bank='cpu'):
        body = struct.pack('<BHHBH', 0, start, start + len(data) - 1, 0, self.bank_id(bank)) + bytes(data)
        self.cmd(0x02, body)
