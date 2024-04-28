import usb_hid
import board
import time
import pwmio
import mfrc522
from adafruit_hid.keyboard import Keyboard
import keyboard_layout_win_sg
from keycode_win_sg import Keycode

keyboard = Keyboard(usb_hid.devices)
keyboard_layout = keyboard_layout_win_sg.KeyboardLayout(keyboard)

# RC522 PINS
rst = board.GP0
miso = board.GP4
mosi = board.GP3
sck = board.GP2
cs = board.GP1

# BUZZER PIN
buzzer = pwmio.PWMOut(board.GP6, variable_frequency=True)
OFF = 0
ON = 2**15
buzzer.frequency = 330

# Initalise RFID object
rfid = mfrc522.MFRC522(sck, mosi, miso, rst, cs)
#rfid.set_antenna_gain(0x07 << 4)

prev_data = ""
prev_time = 0
timeout = 1

while True:
    (status, tag_type) = rfid.request(rfid.REQALL)

    if status == rfid.OK:
        (status, raw_uid) = rfid.anticoll()
        
        if status == rfid.OK:
            rfid_data = ''.join(["{:02x}".format(x) for x in raw_uid])

            if rfid_data != prev_data:
                print(rfid_data)
                prev_data = rfid_data
                rfid_str = rfid_data.upper()
                keyboard_layout.write(rfid_str)
                time.sleep(0.1)
                keyboard.send(Keycode.ENTER)
                
                buzzer.duty_cycle = ON
                time.sleep(0.2)
                buzzer.duty_cycle = OFF
                
                time.sleep(1)

            prev_time = time.monotonic()

    else:
        if time.monotonic() - prev_time > timeout:
            prev_data = ""
