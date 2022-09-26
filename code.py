### Refactored async watch code
#TODO:
#think about how to use encoder position and encoder delta to make behavior work as intended. see if you can fold that all into one Class.
#keep working on GPS time. Dive into the I2C part of the GPS library to find a solution.
import random
import asyncio
import board
import digitalio

#deuglify this later
#sharp_cs = digitalio.DigitalInOut(board.D11)
airlift_cs = digitalio.DigitalInOut(board.D12)
airlift_ready = digitalio.DigitalInOut(board.A5)
airlift_reset = digitalio.DigitalInOut(board.A4)


import time
import pwmio
import busio
from adafruit_pm25.i2c import PM25_I2C
from adafruit_lc709203f import LC709203F, PackSize  # battery monitor library
import adafruit_pcf8523
import displayio
import terminalio
import adafruit_display_text
from adafruit_display_text import label
from adafruit_displayio_sh1107 import SH1107, DISPLAY_OFFSET_ADAFRUIT_128x128_OLED_5297
from adafruit_seesaw import seesaw, rotaryio, digitalio, neopixel ## FIX THIS DOUBLED DIGITALIO
from rainbowio import colorwheel
import adafruit_sht4x
from adafruit_dps310 import DPS310
from adafruit_st7789 import ST7789
import adafruit_imageload
import adafruit_gps
import sharpdisplay
import framebufferio

from adafruit_esp32spi import adafruit_esp32spi
import adafruit_requests as requests

time.sleep(0.2)
displayio.release_displays()


time.sleep(0.2)
i2c = busio.I2C(
    board.SCL, board.SDA, frequency=5500
)  # THIS IS REALLY SLOW I2C- 100000 was default and was still slow. This is so battery sensor works.

# initialize SPI bus
spi_bus = busio.SPI(board.SCK, board.MOSI, board.MISO)

#initialize airlift

airlift = adafruit_esp32spi.ESP_SPIcontrol(spi_bus, airlift_cs, airlift_ready, airlift_reset)

# initialize RTC
days = ("Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday")
rtc = adafruit_pcf8523.PCF8523(i2c)

# initialize PM25 Air Quality
pm25_reset_pin = None
pm25 = PM25_I2C(i2c, pm25_reset_pin)

# initialize humidity/temp sensor
sht = adafruit_sht4x.SHT4x(i2c)
# initialize pressure/temp sensor
dps310 = DPS310(i2c)

# initialize rotary encoder 0
seesaw_0 = seesaw.Seesaw(i2c, addr=0x37)
seesaw_0.pin_mode(24, seesaw_0.INPUT_PULLUP)
button_0 = digitalio.DigitalIO(seesaw_0, 24)
button_held_0 = False
encoder_0 = rotaryio.IncrementalEncoder(seesaw_0)
last_position_0 = 0
enc_0_delta = 0
enc_neopixel_0 = neopixel.NeoPixel(seesaw_0, 6, 1)
enc_neopixel_0.brightness = 0.5


#initialize rotary encoder 1
seesaw_1 = seesaw.Seesaw(i2c, addr=0x36)
seesaw_1.pin_mode(24, seesaw_1.INPUT_PULLUP)
button_1 = digitalio.DigitalIO(seesaw_1, 24)
button_held_1 = False
encoder_1 = rotaryio.IncrementalEncoder(seesaw_1)
last_position_1 = 0
enc_1_delta = 0
enc_neopixel_1 = neopixel.NeoPixel(seesaw_1, 6, 1)
enc_neopixel_1.brightness = 0.5


# initialize battery sensor (the circuitpython implementation is buggy AF - if it crashes on startup, just change the i2c frequency above until it works.
batt_sensor = LC709203F(i2c)
batt_sensor.pack_size = PackSize.MAH3000

# initialize gps
gps = adafruit_gps.GPS_GtopI2C(i2c, debug=False)  # Use I2C interface
gps.send_command(b"PMTK314,0,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0")
gps.send_command(b"PMTK220,2000")

## gps commands found online to do 10HZ updates. Didn't fix the problem of inaccurate time.
# gps.send_command(b"PMTK251,115200*1F")
# gps.send_command(b"PMTK300,100,0,0,0,0*2C")


# daylight savings and timezone correction
dst = True
if dst is True:
    dst_offset = 3600
else:
    dst_offset = 0
est_offset = 18000


# initialize display bus for built-in TFT
display_bus_0 = displayio.FourWire(
    spi_bus, command=board.TFT_DC, chip_select=board.TFT_CS, reset=board.TFT_RESET
)

# initialize display bus for 128x128 Monochrome OLED
display_bus_1 = displayio.FourWire(
    spi_bus, command=board.D6, chip_select=board.D5, reset=board.D9
)

#initialize display bus for 144x168 SHARP memory display FIX DOUBLED DIGITALIO LIBRARY- KINDA UGLY THE WAY IT'S SET UP with command in the imports

sharp_cs = board.D11
framebuffer = sharpdisplay.SharpMemoryFramebuffer(spi_bus, sharp_cs, width=144, height=168, baudrate=8000000)
display_2 = framebufferio.FramebufferDisplay(framebuffer, rotation = 90, auto_refresh = True)



#setup for display 0 backlight
backlight = pwmio.PWMOut(board.TFT_BACKLIGHT, frequency = 5000, duty_cycle = 0)

# setup for width, height and rotation for built-in TFT
WIDTH_0 = 240
HEIGHT_0 = 135
ROTATION_0 = 270
BORDER_0 = 0

display_0 = ST7789(
    display_bus_0,
    rotation=ROTATION_0,
    auto_refresh = False,
    width=WIDTH_0,
    height=HEIGHT_0,
    rowstart=40,
    colstart=53,
)

# setup for width, height and rotation for Monochrome 1.12" 128x128 OLED
WIDTH_1 = 128
HEIGHT_1 = 128
ROTATION_1 = 0
BORDER_1 = 0

display_1 = SH1107(
    display_bus_1,
    width=WIDTH_1,
    height=HEIGHT_1,
    display_offset=DISPLAY_OFFSET_ADAFRUIT_128x128_OLED_5297,
    rotation=ROTATION_1,
    auto_refresh = False
)

# setup colors for 128x128 monochrome OLED
color_palette_1 = displayio.Palette(2)
color_palette_1[0] = 0x000000  # Black
color_palette_1[1] = 0xFFFFFF  # White
font_1 = terminalio.FONT
text_color_1 = 0xFFFFFF


#setup display Groups

splash_0 = displayio.Group()
splash_1 = displayio.Group()
splash_2 = displayio.Group()

#setup fonts for labels
font = terminalio.FONT
text_color = 0xFFFFFF


#setup animated bitmaps for display 0

me_bitmap, me_palette = adafruit_imageload.load(
    "/mesprites.bmp", bitmap=displayio.Bitmap, palette=displayio.Palette
)


me_sprite = displayio.TileGrid(
    me_bitmap, pixel_shader=me_palette, width=1, height=1, tile_width=100, tile_height=112
)


me_group = displayio.Group(scale=1)
me_group.append(me_sprite)
me_group.x = 135
me_group.y = 12

splash_0.append(me_group)

me_group.hidden = True  ## Makes me disappear


nyan_bitmap, nyan_palette = adafruit_imageload.load(
    "/nyancat.bmp", bitmap=displayio.Bitmap, palette=displayio.Palette
)
nyan_sprite = displayio.TileGrid(
    nyan_bitmap,
    pixel_shader=nyan_palette,
    width=1,
    height=1,
    tile_width=32,
    tile_height=32,
)
nyan_group = displayio.Group(scale=3)
nyan_group.append(nyan_sprite)
nyan_group.x = 135
nyan_group.y = 20

splash_0.append(nyan_group)

nyan_group.hidden = True

dino_bitmap, dino_palette = adafruit_imageload.load("/dinorun.bmp", bitmap = displayio.Bitmap, palette = displayio.Palette)
dino_sprite = displayio.TileGrid(
    dino_bitmap,
    pixel_shader=dino_palette,
    width=1,
    height=1,
    tile_width=32,
    tile_height=32,
)
dino_group = displayio.Group(scale=3)
dino_group.append(dino_sprite)
dino_group.x = 135
dino_group.y = 20

splash_0.append(dino_group)

dino_group.hidden = True


#setup text for display 0

d0_text_1 = " "
d0_label_1 = label.Label(font, text=d0_text_1, color=text_color, scale=2)
d0_label_1.x = 0
d0_label_1.y = 0

splash_0.append(d0_label_1)

d0_text_2 = " "
d0_label_2 = label.Label(font, text=d0_text_2, color=text_color, scale=2)
d0_label_2.x = 0
d0_label_2.y = 0

splash_0.append(d0_label_2)

d0_text_3 = " "
d0_label_3 = label.Label(font, text=d0_text_3, color=text_color, scale=2)
d0_label_3.x = 0
d0_label_3.y = 0

splash_0.append(d0_label_3)

d0_text_4 = " "
d0_label_4 = label.Label(font, text=d0_text_4, color=text_color, scale=2)
d0_label_4.x = 0
d0_label_4.y = 0

splash_0.append(d0_label_4)

d0_text_5 = " "
d0_label_5 = label.Label(font, text=d0_text_5, color=text_color, scale=2)
d0_label_5.x = 0
d0_label_5.y = 0

splash_0.append(d0_label_5)

d0_text_6 = " "
d0_label_6 = label.Label(font, text=d0_text_6, color=text_color, scale=2)
d0_label_6.x = 0
d0_label_6.y = 0

splash_0.append(d0_label_6)

d0_text_7 = " "
d0_label_7 = label.Label(font, text=d0_text_7, color=text_color, scale=2)
d0_label_7.x = 0
d0_label_7.y = 0

splash_0.append(d0_label_7)


#setup text for display 1

d1_text_1 = " "
d1_label_1 = label.Label(font, text=d1_text_1, color=text_color, scale=2)
d1_label_1.x = 0
d1_label_1.y = 0

splash_1.append(d1_label_1)

d1_text_2 = " "
d1_label_2 = label.Label(font, text=d1_text_2, color=text_color, scale=2)
d1_label_2.x = 0
d1_label_2.y = 0

splash_1.append(d1_label_2)

d1_text_3 = " "
d1_label_3 = label.Label(font, text=d1_text_3, color=text_color, scale=2)
d1_label_3.x = 0
d1_label_3.y = 0

splash_1.append(d1_label_3)

d1_text_4 = " "
d1_label_4 = label.Label(font, text=d1_text_4, color=text_color, scale=2)
d1_label_4.x = 0
d1_label_4.y = 0

splash_1.append(d1_label_4)

d1_text_5 = " "
d1_label_5 = label.Label(font, text=d1_text_5, color=text_color, scale=2)
d1_label_5.x = 0
d1_label_5.y = 0

splash_1.append(d1_label_5)

d1_text_6 = " "
d1_label_6 = label.Label(font, text=d1_text_6, color=text_color, scale=2)
d1_label_6.x = 0
d1_label_6.y = 0

splash_1.append(d1_label_6)

d1_text_7 = " "
d1_label_7 = label.Label(font, text=d1_text_7, color=text_color, scale=2)
d1_label_7.x = 0
d1_label_7.y = 0

splash_1.append(d1_label_7)



#setup text for display 2

d2_text_1 = " "
d2_label_1 = label.Label(font, text=d2_text_1, color=text_color, scale=2)
d2_label_1.x = 0
d2_label_1.y = 0

splash_2.append(d2_label_1)

d2_text_2 = " "
d2_label_2 = label.Label(font, text=d2_text_2, color=text_color, scale=2)
d2_label_2.x = 0
d2_label_2.y = 0

splash_2.append(d2_label_2)

d2_text_3 = " "
d2_label_3 = label.Label(font, text=d2_text_3, color=text_color, scale=2)
d2_label_3.x = 0
d2_label_3.y = 0

splash_2.append(d2_label_3)

d2_text_4 = " "
d2_label_4 = label.Label(font, text=d2_text_4, color=text_color, scale=2)
d2_label_4.x = 0
d2_label_4.y = 0

splash_2.append(d2_label_4)

d2_text_5 = " "
d2_label_5 = label.Label(font, text=d2_text_5, color=text_color, scale=2)
d2_label_5.x = 0
d2_label_5.y = 0

splash_2.append(d2_label_5)

d2_text_6 = " "
d2_label_6 = label.Label(font, text=d2_text_6, color=text_color, scale=2)
d2_label_6.x = 0
d2_label_6.y = 0

splash_2.append(d2_label_6)

d2_text_7 = " "
d2_label_7 = label.Label(font, text=d2_text_7, color=text_color, scale=2)
d2_label_7.x = 0
d2_label_7.y = 0

splash_2.append(d2_label_7)


#setup bitmaps for display 2
barcode1_bitmap, barcode1_palette = adafruit_imageload.load(
    "/barcode1.bmp", bitmap=displayio.Bitmap, palette=displayio.Palette
)
barcode1_sprite = displayio.TileGrid(
    barcode1_bitmap,
    pixel_shader=barcode1_palette,
    width=1,
    height=1,
    tile_width=168,
    tile_height=144,
)
barcode1_group = displayio.Group(scale=1)
barcode1_group.append(barcode1_sprite)
barcode1_group.x = 0
barcode1_group.y = 0

splash_2.append(barcode1_group)

qrcode1_bitmap, qrcode1_palette = adafruit_imageload.load("/qrcode1.bmp", bitmap = displayio.Bitmap, palette = displayio.Palette)
qrcode1_sprite = displayio.TileGrid(
    qrcode1_bitmap,
    pixel_shader=barcode1_palette,
    width=1,
    height=1,
    tile_width=120,
    tile_height=121,
)
qrcode1_group = displayio.Group(scale=1)
qrcode1_group.append(qrcode1_sprite)
qrcode1_group.x = 24
qrcode1_group.y = 12

splash_2.append(qrcode1_group)


barcode1_group.hidden = True
qrcode1_group.hidden = True

#show displays
display_0.show(splash_0)
display_1.show(splash_1)
display_2.show(splash_2)


# setup variables to manage flow control between watch "screens"


#class definition to hold sensor values

class Sensorvals:
    def __init__(self):
        # temperature/pressure/humidity
        self.temperature = None
        self.pressure = None
        self.humidity = None

        # air quality
        self.p03 = None  # 0.3 micron particles
        self.p05 = None  # 0.5 micron particles
        self.p10 = None  # 1.0 micron particles
        self.p25 = None  # 2.5 micron particles
        self.p50 = None  # 5.0 micron particles
        self.p100 = None  # 10 micron particles
        self.pm10 = None  # PM 1.0 value
        self.pm25 = None  # PM 2.5 value
        self.pm100 = None  # PM 10 value

        #battery level
        self.voltage = None
        self.batt_percent = None

#create Sensorvals instance
sensorvals = Sensorvals()


#class definition for generic value passing
class Valpass:
    """class used to pass values between coroutines"""

    def __init__(self, value):
        self.value = value

class Rotary_state:
    """class used to record and pass rotary encoder states"""
    def __init__(self):
       self.delta = 0
       self.button = False

#create two rotary states (when you get the next rotary encoder)
rotary_state_0 = Rotary_state()
rotary_state_1 = Rotary_state()

class Programstate:
    """ class to hold the various screen states """
    def __init__(self):
        self.d0 = 0 #main state of screen 0
        self.d1 = 0 #main state of screen 1

#create Programstate instance called program_state for state switching.
program_state = Programstate()

async def state_switcher(program_state):
    d0_state_count = 4
    d1_state_count = 4
    try:
        init_pos_0 = encoder_0.position
        init_pos_1 = encoder_1.position
    except:
        print("state switcher fail 1")
    while True:
        try:
            if encoder_0.position != init_pos_0:
                delta_0 = encoder_0.position - init_pos_0
                program_state.d0 = (delta_0 + program_state.d0)%d0_state_count
                print("Program State d0: " + str(program_state.d0))
                init_pos_0 = encoder_0.position
                program_state.d1 = 0 # this line resets the menu for screen 1
                if program_state.d0 == 0:
                    d1_state_count = 4
                if program_state.d0 == 1:
                    d1_state_count = 2
                if program_state.d0 == 2:
                    d1_state_count = 3
                if program_state.d0 == 3:
                    d1_state_count = 2
            if encoder_1.position != init_pos_1:
                delta_1 = encoder_1.position - init_pos_1
                program_state.d1 = (delta_1 + program_state.d1)%d1_state_count
                print("Program State d1: " + str(program_state.d1))
                init_pos_1 = encoder_1.position
        except:
            print("state switcher fail.")
        await asyncio.sleep(0)





#display 0 default date time screen updates
async def d0_datetime(program_state):
    while True:
        if program_state.d0 == 0:
            d0_label_1.hidden = False
            d0_label_2.hidden = False
            d0_label_3.hidden = False
            d0_label_4.hidden = False
            d0_label_5.hidden = False
            d0_label_6.hidden = False
            d0_label_7.hidden = True

            t = rtc.datetime
            if t.tm_hour == 0:
                hour_12 = 12
                ampm = "AM"
            elif t.tm_hour > 0 and t.tm_hour < 12:
                hour_12 = t.tm_hour
                ampm = "AM"
            elif t.tm_hour == 12:
                hour_12 = t.tm_hour
                ampm = "PM"
            elif t.tm_hour > 12:
                hour_12 = t.tm_hour % 12
                ampm = "PM"
            d0_label_1.scale = 2
            d0_label_1.x = 0
            d0_label_1.y = 8
            d0_label_1.text = "%s" % (days[t.tm_wday]) + ","

            d0_label_2.scale = 2
            d0_label_2.x = 10
            d0_label_2.y = 30
            d0_label_2.text = "%02d/%02d/%d" % (t.tm_mon, t.tm_mday, t.tm_year)

            d0_label_3.scale = 3
            d0_label_3.x = 13
            d0_label_3.y = 60
            d0_label_3.text = "%02d:%02d" % (hour_12, t.tm_min)

            d0_label_4.scale = 2
            d0_label_4.x = 105
            d0_label_4.y = 64
            d0_label_4.text = ampm

            d0_label_5.scale = 2
            d0_label_5.x = 56
            d0_label_5.y = 95
            d0_label_5.text = "%02d" % (t.tm_sec)

            d0_label_6.scale = 1
            d0_label_6.x = 30
            d0_label_6.y = 124
            try:
                d0_label_6.text = "Battery: %0.3f Volts / %0.1f%%" % (sensorvals.voltage, sensorvals.batt_percent)
            except:
                d0_label_6.text = "Battery Read Fail."

            d0_label_7.scale = 2
            d0_label_7.x = 0
            d0_label_7.y = 0
            d0_label_7.text = ""

            display_0.refresh()
        await asyncio.sleep(0.5)

#display 0 nyancat animation

async def d0_nyancat(program_state):
    nyandex = 0
    while True:
        if program_state.d0 == 0:
            nyan_group.hidden = False
            nyan_sprite[0] = nyandex
            nyandex = (nyandex + 1) % 11
            display_0.refresh()
        else:
            nyan_group.hidden = True
        await asyncio.sleep(0.2)

#display 0 wifi mode

async def d0_wifi(program_state):
    while True:
        if program_state.d0 == 1:
            nyan_group.hidden = True

            d0_label_1.hidden = False
            d0_label_2.hidden = True
            d0_label_3.hidden = True
            d0_label_4.hidden = True
            d0_label_5.hidden = True
            d0_label_6.hidden = True
            d0_label_7.hidden = True

            d0_label_1.text = "Wifi Functions"
            d0_label_1.scale = 2
            d0_label_1.x = 0
            d0_label_1.y = 15

            display_0.refresh()
        await asyncio.sleep(0.2)


#display 0 Barcode Mode

async def d0_barcodes(program_state):
    while True:
        if program_state.d0 == 2:
            nyan_group.hidden = True

            d0_label_1.hidden = False
            d0_label_2.hidden = True
            d0_label_3.hidden = True
            d0_label_4.hidden = True
            d0_label_5.hidden = True
            d0_label_6.hidden = True
            d0_label_7.hidden = True

            d0_label_1.text = "Barcode Selection"
            d0_label_1.scale = 2
            d0_label_1.x = 0
            d0_label_1.y = 15

            display_0.refresh()
        await asyncio.sleep(0.2)

#display 0 GPS Mode

async def d0_gps(program_state):
    while True:
        if program_state.d0 == 3:
            nyan_group.hidden = True

            d0_label_1.hidden = False
            d0_label_2.hidden = False
            d0_label_3.hidden = False
            d0_label_4.hidden = True
            d0_label_5.hidden = True
            d0_label_6.hidden = True
            d0_label_7.hidden = True

            d0_label_1.text = "GPS Status"
            d0_label_1.scale = 2
            d0_label_1.x = 0
            d0_label_1.y = 15

            d0_label_2.scale = 1
            d0_label_2.x = 0
            d0_label_2.y = 45

            try:
                rtc_est_seconds = time.mktime(rtc.datetime)
            except:
                rtc_est_seconds = "RTC fail!"

            d0_label_3.scale = 1
            d0_label_3.x = 0
            d0_label_3.y = 75
            d0_label_3.text = "RTC EST: " + str(rtc_est_seconds)

            try:
                gps.update()
            except:
                print("gps update fail.")
            print(gps.nmea_sentence)
            if gps.timestamp_utc:
                print ("gps time fix acquired!")
                try:
                    gps_time = gps.timestamp_utc
                    gps_utc_seconds = time.mktime(gps_time)
                    gps_est_seconds = gps_utc_seconds - est_offset + dst_offset
                    #rtc.datetime = time.localtime(gps_est_seconds)

                    d0_label_2.text = "GPS EST: " + str(gps_est_seconds)
                except:
                    d0_label_2.text = "Parse Error."
            else:
                d0_label_2.text = "No Fix..."
            display_0.refresh()
        await asyncio.sleep(0.2)

async def d1_blank(program_state):
    while True:
        if (program_state.d1 == 0):
            d1_label_1.hidden = True
            d1_label_2.hidden = True
            d1_label_3.hidden = True
            d1_label_4.hidden = True
            d1_label_5.hidden = True
            d1_label_6.hidden = True
            d1_label_7.hidden = True
        display_1.refresh()
        await asyncio.sleep(0.5)

async def d2_blank(program_state):
    while True:
        if (program_state.d0 == 2 and program_state.d1 == 0):
            barcode1_group.hidden = True
            qrcode1_group.hidden = True
            display_2.refresh()
        await asyncio.sleep(0.2)



async def d1_datetime(program_state):
    while True:
        if program_state.d0 == 0 and program_state.d1 == 1:
            d1_label_1.hidden = False

            d1_label_2.hidden = False

            d1_label_3.hidden = False

            d1_label_4.hidden = False

            d1_label_5.hidden = False

            d1_label_6.hidden = False

            d1_label_7.hidden = False
            t = rtc.datetime
            if t.tm_hour == 0:
                hour_12 = 12
                ampm = "AM"
            elif t.tm_hour > 0 and t.tm_hour < 12:
                hour_12 = t.tm_hour
                ampm = "AM"
            elif t.tm_hour == 12:
                hour_12 = t.tm_hour
                ampm = "PM"
            elif t.tm_hour > 12:
                hour_12 = t.tm_hour % 12
                ampm = "PM"
            d1_label_1.scale = 2
            d1_label_1.x = 0
            d1_label_1.y = 8
            d1_label_1.text = "%s" % (days[t.tm_wday]) + ","

            d1_label_2.scale = 2
            d1_label_2.x = 10
            d1_label_2.y = 30
            d1_label_2.text = "%02d/%02d/%d" % (t.tm_mon, t.tm_mday, t.tm_year)

            d1_label_3.scale = 3
            d1_label_3.x = 13
            d1_label_3.y = 60
            d1_label_3.text = "%02d:%02d" % (hour_12, t.tm_min)

            d1_label_4.scale = 2
            d1_label_4.x = 105
            d1_label_4.y = 64
            d1_label_4.text = ampm

            d1_label_5.scale = 2
            d1_label_5.x = 56
            d1_label_5.y = 95
            d1_label_5.text = "%02d" % (t.tm_sec)

            d1_label_6.scale = 1
            d1_label_6.x = 0
            d1_label_6.y = 120
            try:
                d1_label_6.text = "Batt: %0.3fV / %0.1f%%" % (sensorvals.voltage, sensorvals.batt_percent)
            except:
                d1_label_6.text = "   Battery Read Fail."

            d1_label_7.scale = 2
            d1_label_7.x = 0
            d1_label_7.y = 0
            d1_label_7.text = ""
            display_1.refresh()
        await asyncio.sleep(0.5)

async def d1_pm25(program_state, sensorvals):
    while True:
        if program_state.d0 == 0 and program_state.d1 == 2:
            d1_label_1.hidden = False
            d1_label_2.hidden = False
            d1_label_3.hidden = True
            d1_label_4.hidden = True
            d1_label_5.hidden = True
            d1_label_6.hidden = True
            d1_label_7.hidden = True

            d1_label_1.scale = 2
            d1_label_1.x = 0
            d1_label_1.y = 8
            d1_label_1.text = "PM 2.5:"

            d1_label_2.scale = 5
            d1_label_2.x = 10
            d1_label_2.y = 60
            d1_label_2.text = str(sensorvals.pm25)

            display_1.refresh()
        await asyncio.sleep(1.0)

async def d1_tph(program_state, sensorvals):
    while True:
        if program_state.d0 == 0 and program_state.d1 == 3:
            d1_label_1.hidden = False
            d1_label_2.hidden = False
            d1_label_3.hidden = False
            d1_label_4.hidden = False
            d1_label_5.hidden = False
            d1_label_6.hidden = True
            d1_label_7.hidden = True

            d1_label_1.scale = 1
            d1_label_1.x = 0
            d1_label_1.y = 12
            try:
                d1_label_1.text = "Tf: " + str(sensorvals.temperature * (9/5)+32) + "F"
            except:
                d1_label_1.text = "Tf: Sensor Failure."

            d1_label_2.scale = 1
            d1_label_2.x = 0
            d1_label_2.y = 36
            try:
                d1_label_2.text = "Tc: " + str(sensorvals.temperature) + "C"
            except:
                d1_label_2.text = "Tc: Sensor Failure."

            d1_label_3.scale = 1
            d1_label_3.x = 0
            d1_label_3.y = 60
            try:
                d1_label_3.text = "Tk: " + str(sensorvals.temperature + 273.15) + "K"
            except:
                d1_label_3.text = "Tk: Sensor Failure."

            d1_label_4.scale = 1
            d1_label_4.x = 0
            d1_label_4.y = 84
            try:
                d1_label_4.text = "Hu: " + str(sensorvals.humidity) + "%"
            except:
                d1_label_4.text = "Hu: Sensor Failure."

            d1_label_5.scale = 1
            d1_label_5.x = 0
            d1_label_5.y = 108
            try:
                d1_label_5.text = "Pr: " + str(sensorvals.pressure) + "hPA"
            except:
                d1_label_5.text = "Pr: Sensor Failure."

            display_1.refresh()
        await asyncio.sleep(1.0)


async def d1_gps_timeset(program_state):
    button_1_held = False
    gps_set = False
    dst_offset = 3600
    est_offset = 18000
    while True:
        if not (program_state.d0 == 3 and program_state.d1 == 1):
            gps_set = False
        if program_state.d0 == 3 and program_state.d1 == 1:
            d1_label_1.hidden = False
            d1_label_2.hidden = False
            d1_label_3.hidden = True
            d1_label_4.hidden = True
            d1_label_5.hidden = True
            d1_label_6.hidden = True
            d1_label_7.hidden = True

            d1_label_1.scale = 1
            d1_label_1.x = 0
            d1_label_1.y = 18

            d1_label_2.scale = 1
            d1_label_2.x = 0
            d1_label_2.y = 4
            if not button_1.value and not button_1_held:
                button_1_held = True
                d1_label_1.text ="Release!"
                d1_label_2.text = "GPS => RTC timeset"
                display_1.refresh()
                print("Button 1 pressed")
                gps_set = True
            if button_1.value and button_1_held:
                button_1_held = False
                d1_label_1.text = ""
                display_1.refresh()
                print("Button 1 released")
                try:
                    d1_label_1.text = ""
                    gps_time = gps.datetime
                    gps_utc_seconds = time.mktime(gps_time)
                    gps_est_seconds = gps_utc_seconds - est_offset + dst_offset
                    rtc.datetime = time.localtime(gps_est_seconds)
                    d1_label_2.text = "RTC set!"
                    display_1.refresh()
                except:
                    print("GPS => RTC time set fail.")
            if gps_set == False:
                d1_label_1.text = "Click to set RTC time!"
                d1_label_2.text = "GPS => RTC timeset"
                display_1.refresh()
        await asyncio.sleep(0.2)


async def d2_barcodes(program_state):
    while True:
        if program_state.d0 == 2:
            if program_state.d1 == 1:
                d2_label_1.hidden = True
                d2_label_2.hidden = True
                d2_label_3.hidden = True
                d2_label_4.hidden = True
                d2_label_5.hidden = True
                d2_label_6.hidden = True
                d2_label_7.hidden = True

                barcode1_group.hidden = False
                qrcode1_group.hidden = True
            if program_state.d1 == 2:
                d2_label_1.hidden = True
                d2_label_2.hidden = True
                d2_label_3.hidden = True
                d2_label_4.hidden = True
                d2_label_5.hidden = True
                d2_label_6.hidden = True
                d2_label_7.hidden = True

                barcode1_group.hidden = True
                qrcode1_group.hidden = False
        await asyncio.sleep(1.0)


async def d2_pm25(program_state, sensorvals):
    while True:
        if program_state.d0 == 0:
            d2_label_1.hidden = False
            d2_label_2.hidden = False
            d2_label_3.hidden = True
            d2_label_4.hidden = True
            d2_label_5.hidden = True
            d2_label_6.hidden = True
            d2_label_7.hidden = True

            d2_label_1.scale = 2
            d2_label_1.x = 0
            d2_label_1.y = 8
            d2_label_1.text = "PM 2.5:"

            d2_label_2.scale = 7
            d2_label_2.x = 10
            d2_label_2.y = 80
            d2_label_2.text = str(sensorvals.pm25)

            #display_2.refresh(target_frames_per_second = 1, minimum_frames_per_second = 0) test to see if can turn auto off. nope.
            #print("display 2 refreshed.")
        await asyncio.sleep(1.0)

async def poll_battery(program_state, batt_sensor, sensorvals):
    while True:
        if program_state.d0 == 0:
            try:
                sensorvals.voltage = batt_sensor.cell_voltage
                sensorvals.batt_percent = batt_sensor.cell_percent
            except:
                sensorvals.voltage = None
                sensorvals.batt_percent = None
        await asyncio.sleep(2.0)



# rotary encoder functions

async def monitor_rotary(rotary, button, rotary_state):
    position = 0
    last_position = 0
    button_held = False

    while True:
        try:
            position = rotary.position
            if position != last_position:
                rotary_delta = position - last_position
                last_position = position
                rotary_state.delta = rotary_delta
                print("Delta Position: {}".format(rotary_delta))
            if not button.value and not button_held:
                button_held = True
                rotary_state.button = True
                print("Button pressed")
            if button.value and button_held:
                button_held = False
                rotary_state.button = False
                print("Button released")
        except:
            print("could not read rotary encoder")
        await asyncio.sleep(0)


#function to poll air quality
async def poll_pmsa003i(program_state, aqsensor, sensorvals):
    while True:
        if program_state.d0 == 0:
            try:
                aqdata = aqsensor.read()
                sensorvals.p03 = aqdata["particles 03um"]
                sensorvals.p05 = aqdata["particles 05um"]
                sensorvals.p10 = aqdata["particles 10um"]
                sensorvals.p25 = aqdata["particles 25um"]
                sensorvals.p50 = aqdata["particles 50um"]
                sensorvals.p100 = aqdata["particles 100um"]
                sensorvals.pm10 = aqdata["pm10 standard"]
                sensorvals.pm25 = aqdata["pm25 standard"]
                sensorvals.pm100 = aqdata["pm100 standard"]
            except:
                print("Air quality read failure.")
                sensorvals.p03 = None
                sensorvals.p05 = None
                sensorvals.p10 = None
                sensorvals.p25 = None
                sensorvals.p50 = None
                sensorvals.p100 = None
                sensorvals.pm10 = None
                sensorvals.pm25 = None
                sensorvals.pm100 = None
        await asyncio.sleep(1.0)

#function to poll SHT40 sensor
async def poll_sht40(program_state, shtsensor, sensorvals):
    while True:
        if program_state.d0 == 0:
            try:
                sensorvals.temperature, sensorvals.humidity = shtsensor.measurements
            except:
                print("SHT40 read failure.")
                sensorvals.temperature = None
                sensorvals.humidity = None
        await asyncio.sleep (1.0)

#function to poll DPS310 sensor
async def poll_dps310(program_state, dps_sensor, sensorvals):
    while True:
        if program_state.d0 == 0:
            try:
                sensorvals.pressure = dps_sensor.pressure
            except:
                print("DPS310 read failure.")
                sensorvals.pressure = None
        await asyncio.sleep(1.0)


#test function
async def test_sensor_prints(sensorvals):
    while True:
        try:
            print(sensorvals.pm25)
            print(sensorvals.temperature)
            print(sensorvals.pressure)
            print(" ")
        except:
            print("sensor value error.")
        await asyncio.sleep(1.0)



#turn to backlight
async def click_backlight():
    prevtime = time.mktime(rtc.datetime)
    try:
        init_pos_0 = encoder_0.position
        init_pos_1 = encoder_1.position
    except:
        print("click backlight rotary read fail 1")
    backlight.duty_cycle = 5000
    while True:
        try:
            if encoder_0.position != init_pos_0:
                backlight.duty_cycle = 65000
                prevtime = time.mktime(rtc.datetime)
                init_pos_0 = encoder_0.position
            if encoder_1.position != init_pos_1:
                backlight.duty_cycle = 65000
                prevtime = time.mktime(rtc.datetime)
                init_pos_1 = encoder_1.position
            if time.mktime(rtc.datetime) - prevtime > 4 and backlight.duty_cycle > 5000:
                backlight.duty_cycle = backlight.duty_cycle - 5000
        except:
            print("click backlight fail.")
        await asyncio.sleep(0.2)

async def airlift_scan_networks(program_state):
    button_1_held = False
    scan_results = False
    while True:
        if not (program_state.d0 == 1 and program_state.d1 == 1):
            scan_results = False
        if program_state.d0 == 1 and program_state.d1 == 1:
            d1_label_1.hidden = False
            d1_label_2.hidden = False
            d1_label_3.hidden = True
            d1_label_4.hidden = True
            d1_label_5.hidden = True
            d1_label_6.hidden = True
            d1_label_7.hidden = True

            d1_label_1.scale = 1
            d1_label_1.x = 0
            d1_label_1.y = 18

            d1_label_2.scale = 1
            d1_label_2.x = 0
            d1_label_2.y = 4
            #display_1.refresh()

            #print("button_0: " + str(button_0.value))
            #print("button_1: " + str(button_1.value))
            #print(" ")
            if not button_1.value and not button_1_held:
                button_1_held = True
                d1_label_1.text ="Release!"
                d1_label_2.text = "2.4GHz SSID SCAN..."
                display_1.refresh()
                print("Button 1 pressed")
                scan_results = True
            if button_1.value and button_1_held:
                button_1_held = False
                d1_label_1.text = ""
                display_1.refresh()
                print("Button 1 released")
                try:
                    d1_label_1.text = "Scanning..."
                    display_1.refresh()
                    ap_list_string = ""
                    for ap in airlift.scan_networks():
                        print("\t%s\t\tRSSI: %d" % (str(ap['ssid'], 'utf-8'), ap['rssi']))
                        ap_list_string = ap_list_string + ("%s\tRSSI: %d" % (str(ap['ssid'], 'utf-8'), ap['rssi'])) + "\n"
                    d1_label_1.text = ap_list_string
                    d1_label_2.text = "2.4GHz Scan Results:"
                    display_1.refresh()
                except:
                    print("airlift scan fail")
            if scan_results == False:
                d1_label_1.text = "Click to scan! 0_0"
                d1_label_2.text = "2.4GHz SSID SCAN..."
        await asyncio.sleep(0.2)

"""
## setup test code for displays (GPS debugging)
##
text_color = 0xFFFFFF
font = terminalio.FONT

splash_0 = displayio.Group()

rtc_time_text = (" ")
rtc_time_disp = label.Label(font, text=rtc_time_text, color=text_color, scale=2)
rtc_time_disp.x = 0
rtc_time_disp.y = 10

gps_time_text = (" ")
gps_time_disp = label.Label(font, text=gps_time_text, color=text_color, scale=2)
gps_time_disp.x = 0
gps_time_disp.y = 40

splash_0.append(gps_time_disp)
splash_0.append(rtc_time_disp)

splash_1 = displayio.Group()
nmea_text = (" ")
nmea_disp = label.Label(font, text = nmea_text, color = text_color, scale = 1)
nmea_disp.x = 0
nmea_disp.y = 10

splash_1.append(nmea_disp)



##
##
"""
# display_0.show(splash_0)
# display_1.show(splash_1)


# screen switch functions

# async def screen_flow():


async def gps_rtc_timeset(gps):
    dst_offset = 3600
    est_offset = 18000
    prev_gps_time = rtc.datetime
    gps_time = rtc.datetime
    while True:
    #try:
        while gps.update(): # the runs forever while gps.update is True. Need to dive into the gps i2c library to find out how to directly parse sentences to avoid this problem.
            print(gps.nmea_sentence)
            gps_time = gps.datetime
        if gps.has_fix and gps_time != prev_gps_time:
            print ("gps time fix acquired!")
            gps_utc_seconds = time.mktime(gps_time)
            gps_est_seconds = gps_utc_seconds - est_offset + dst_offset
            rtc.datetime = time.localtime(gps_est_seconds)
            prev_gps_time = gps_time
    #except:
        #print("GPS RTC time set fail")
        await asyncio.sleep(1.0)







# async main function


async def main():  # Don't forget the async!
    click_backlight_task = asyncio.create_task(click_backlight())
    state_switcher_task = asyncio.create_task(state_switcher(program_state))
    d0_datetime_task = asyncio.create_task(d0_datetime(program_state))
    d0_wifi_task = asyncio.create_task(d0_wifi(program_state))
    d0_barcodes_task = asyncio.create_task(d0_barcodes(program_state))
    d0_gps_task = asyncio.create_task(d0_gps(program_state))
    d2_barcodes_task = asyncio.create_task(d2_barcodes(program_state))
    d1_blank_task = asyncio.create_task(d1_blank(program_state))
    d1_datetime_task = asyncio.create_task(d1_datetime(program_state))
    d1_pm25_task = asyncio.create_task(d1_pm25(program_state, sensorvals))
    d1_tph_task = asyncio.create_task(d1_tph(program_state, sensorvals))
    d1_gps_timeset_task = asyncio.create_task(d1_gps_timeset(program_state))
    #d2_pm25_task = asyncio.create_task(d2_pm25(program_state, sensorvals))
    d2_blank_task = asyncio.create_task(d2_blank(program_state))
    d0_nyancat_task = asyncio.create_task(d0_nyancat(program_state))
    poll_battery_task = asyncio.create_task(poll_battery(program_state, batt_sensor, sensorvals))
    #gps_rtc_timeset_task = asyncio.create_task(gps_rtc_timeset(gps))
    #rotary_0_task = asyncio.create_task(monitor_rotary(encoder_0, button_0, rotary_state_0))
    poll_pmsa003i_task = asyncio.create_task(poll_pmsa003i(program_state, pm25, sensorvals))
    poll_sht40_task = asyncio.create_task(poll_sht40(program_state, sht, sensorvals))
    poll_dps310_task = asyncio.create_task(poll_dps310(program_state, dps310, sensorvals))
    airlift_scan_networks_task = asyncio.create_task(airlift_scan_networks(program_state))
    #test_sensor_prints_task = asyncio.create_task(test_sensor_prints(sensorvals))
    await asyncio.gather(state_switcher_task)
    #    await asyncio.gather(gps_timeset_task)  # Don't forget the await!
    print("done")



asyncio.run(main())
# Write your code here :-)
