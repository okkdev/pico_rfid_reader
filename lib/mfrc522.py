import board
import busio
from digitalio import DigitalInOut, Direction, Pull
import adafruit_bus_device.spi_device as spi_device


class MFRC522:
    DEBUG = False
    OK = 0
    NOTAGERR = 1
    ERR = 2

    NTAG_213 = 213
    NTAG_215 = 215
    NTAG_216 = 216
    NTAG_NONE = 0

    REQIDL = 0x26
    REQALL = 0x52
    AUTHENT1A = 0x60
    AUTHENT1B = 0x61

    PICC_ANTICOLL1 = 0x93
    PICC_ANTICOLL2 = 0x95
    PICC_ANTICOLL3 = 0x97

    def __init__(self, sck, mosi, miso, rst, cs, baudrate=1000000, spi_id=0):
        self.sck = sck
        self.mosi = mosi
        self.miso = miso
        self.rst = DigitalInOut(rst)
        self.rst.direction = Direction.OUTPUT
        self.cs = DigitalInOut(cs)
        self.cs.direction = Direction.OUTPUT

        self.rst.value = False
        self.cs.value = True
        self.NTAG = 0
        self.NTAG_MaxPage = 0

        self.spi = busio.SPI(sck, MOSI=mosi, MISO=miso)
        while not self.spi.try_lock():
            pass
        self.spi.configure(baudrate=baudrate, polarity=0, phase=0)
        self.spi.unlock()

        self.spi_device = spi_device.SPIDevice(self.spi, self.cs)

        self.rst.value = True
        self.init()

    def _wreg(self, reg, val):
        with self.spi_device as spi:
            spi.write(bytearray([0xFF & ((reg << 1) & 0x7E), 0xFF & val]))

    def _rreg(self, reg):
        with self.spi_device as spi:
            spi.write(bytearray([0xFF & (((reg << 1) & 0x7E) | 0x80)]))
            result = bytearray(1)
            spi.readinto(result)
            return result[0]

    def _sflags(self, reg, mask):
        self._wreg(reg, self._rreg(reg) | mask)

    def _cflags(self, reg, mask):
        self._wreg(reg, self._rreg(reg) & (~mask))

    def _tocard(self, cmd, send):
        recv = []
        bits = irq_en = wait_irq = n = 0
        stat = self.ERR

        if cmd == 0x0E:
            irq_en = 0x12
            wait_irq = 0x10
        elif cmd == 0x0C:
            irq_en = 0x77
            wait_irq = 0x30

        self._wreg(0x02, irq_en | 0x80)
        self._cflags(0x04, 0x80)
        self._sflags(0x0A, 0x80)
        self._wreg(0x01, 0x00)

        for c in send:
            self._wreg(0x09, c)
        self._wreg(0x01, cmd)

        if cmd == 0x0C:
            self._sflags(0x0D, 0x80)

        i = 2000
        while True:
            n = self._rreg(0x04)
            i -= 1
            if not ((i != 0) and not (n & 0x01) and not (n & wait_irq)):
                break

        self._cflags(0x0D, 0x80)

        if i:
            if (self._rreg(0x06) & 0x1B) == 0x00:
                stat = self.OK

                if n & irq_en & 0x01:
                    stat = self.NOTAGERR
                elif cmd == 0x0C:
                    n = self._rreg(0x0A)
                    lbits = self._rreg(0x0C) & 0x07
                    if lbits != 0:
                        bits = (n - 1) * 8 + lbits
                    else:
                        bits = n * 8

                    if n == 0:
                        n = 1
                    elif n > 16:
                        n = 16

                    for _ in range(n):
                        recv.append(self._rreg(0x09))
            else:
                stat = self.ERR

        return stat, recv, bits

    def _crc(self, data):
        self._cflags(0x05, 0x04)
        self._sflags(0x0A, 0x80)

        for c in data:
            self._wreg(0x09, c)

        self._wreg(0x01, 0x03)

        i = 0xFF
        while True:
            n = self._rreg(0x05)
            i -= 1
            if not ((i != 0) and not (n & 0x04)):
                break

        return [self._rreg(0x22), self._rreg(0x21)]

    def init(self):
        self.reset()
        self._wreg(0x2A, 0x8D)
        self._wreg(0x2B, 0x3E)
        self._wreg(0x2D, 30)
        self._wreg(0x2C, 0)
        self._wreg(0x15, 0x40)
        self._wreg(0x11, 0x3D)
        self.antenna_on()

    def reset(self):
        self._wreg(0x01, 0x0F)

    def antenna_on(self, on=True):
        if on and not (self._rreg(0x14) & 0x03):
            self._sflags(0x14, 0x03)
        else:
            self._cflags(0x14, 0x03)

    def request(self, mode):
        self._wreg(0x0D, 0x07)
        (stat, recv, bits) = self._tocard(0x0C, [mode])

        if (stat != self.OK) | (bits != 0x10):
            stat = self.ERR

        return stat, bits

    def anticoll(self, anticolN):
        ser_chk = 0
        ser = [anticolN, 0x20]

        self._wreg(0x0D, 0x00)
        (stat, recv, bits) = self._tocard(0x0C, ser)

        if stat == self.OK:
            if len(recv) == 5:
                for i in range(4):
                    ser_chk = ser_chk ^ recv[i]
                if ser_chk != recv[4]:
                    stat = self.ERR
            else:
                stat = self.ERR

        return stat, recv

    def PcdSelect(self, serNum, anticolN):
        backData = []
        buf = []
        buf.append(anticolN)
        buf.append(0x70)
        for i in serNum:
            buf.append(i)
        pOut = self._crc(buf)
        buf.append(pOut[0])
        buf.append(pOut[1])
        (status, backData, backLen) = self._tocard(0x0C, buf)
        if (status == self.OK) and (backLen == 0x18):
            return 1
        else:
            return 0

    def SelectTag(self, uid):
        byte5 = 0
        for i in uid:
            byte5 = byte5 ^ i
        puid = uid + [byte5]
        if self.PcdSelect(puid, self.PICC_ANTICOLL1) == 0:
            return (self.ERR, [])
        return (self.OK, uid)

    def tohexstring(self, v):
        s = "["
        for i in v:
            if i != v[0]:
                s = s + ", "
            s = s + "0x{:02X}".format(i)
        s = s + "]"
        return s

    def SelectTagSN(self):
        valid_uid = []
        (status, uid) = self.anticoll(self.PICC_ANTICOLL1)
        if status != self.OK:
            return (self.ERR, [])

        if self.DEBUG:
            print("anticol(1) {}".format(uid))
        if self.PcdSelect(uid, self.PICC_ANTICOLL1) == 0:
            return (self.ERR, [])
        if self.DEBUG:
            print("pcdSelect(1) {}".format(uid))

        if uid[0] == 0x88:
            valid_uid.extend(uid[1:4])
            (status, uid) = self.anticoll(self.PICC_ANTICOLL2)
            if status != self.OK:
                return (self.ERR, [])
            if self.DEBUG:
                print("anticol(2) {}".format(uid))
            if self.PcdSelect(uid, self.PICC_ANTICOLL2) == 0:
                return (self.ERR, [])
            if self.DEBUG:
                print("pcdSelect(2) {}".format(uid))

        valid_uid.extend(uid[:4])

        if uid[0] == 0x88:
            (status, uid) = self.anticoll(self.PICC_ANTICOLL3)
            if status != self.OK:
                return (self.ERR, [])
            if self.DEBUG:
                print("anticol(3) {}".format(uid))
            if self.PcdSelect(uid, self.PICC_ANTICOLL3) == 0:
                return (self.ERR, [])
            if self.DEBUG:
                print("pcdSelect(3) {}".format(uid))
            valid_uid.extend(uid[:5])

        if self.DEBUG:
            print("Valid UID {}".format(self.tohexstring(valid_uid)))

        if self.DEBUG:
            print("Requesting tag type")
        (status, ATQA) = self.request(self.REQIDL)
        if self.DEBUG:
            print("Request ATQA {} (stat: {})".format(ATQA, status))

        if ATQA == 0x0044:
            self.NTAG = self.NTAG_213
            self.NTAG_MaxPage = 44
        elif ATQA == 0x0042:
            self.NTAG = self.NTAG_215
            self.NTAG_MaxPage = 129
        elif ATQA == 0x0043:
            self.NTAG = self.NTAG_216
            self.NTAG_MaxPage = 231
        else:
            self.NTAG = self.NTAG_NONE

        return (self.OK, valid_uid)
