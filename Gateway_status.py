import requests
import os
from time import sleep, strftime, time
import serial
import logging
import RPi.GPIO as GPIO
import serial.tools.list_ports
import fnmatch
from threading import Thread
import netifaces as ni
import subprocess

import APN

#from gpiozero import CPUTemperature

main_sense_pin = 13
pulse_pin = 21
enable_telit = 19
pulse = True
port_count = 0
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
GPIO.setup(main_sense_pin, GPIO.IN, GPIO.PUD_DOWN)
GPIO.setup(pulse_pin, GPIO.OUT, initial=GPIO.LOW)
GPIO.setup(enable_telit, GPIO.OUT, initial=GPIO.LOW)

logging.basicConfig(filename='Gateway_status.log', filemode='a', format='%(asctime)s - %(message)s',
                    datefmt='%d-%b-%y %H:%M:%S', level=logging.ERROR)

#cpu = CPUTemperature()

sleep(10)
GPIO.output(enable_telit, GPIO.HIGH)
sleep(5)
GPIO.output(enable_telit, GPIO.LOW)
sleep(20)

def enable_modem():
    GPIO.output(enable_telit, GPIO.HIGH)
    sleep(5)
    GPIO.output(enable_telit, GPIO.LOW)
    sleep(20)



def main_sense():
    global pulse
    pulse = True
    mains_count = 0
    while True:
        if GPIO.input(main_sense_pin) == 0:
            mains_count = mains_count + 1
            if mains_count == 5:
                logging.error('Mains sense Low')
                pulse = False
                sleep(8)
                try:
                    os.system('sudo -S shutdown -h now')
                except Exception as e:
                    logging.error(e)
                    os.system('sudo -S shutdown -h now')
            sleep(5)
        else:
            mains_count = 0
            sleep(5)


def pulse_gen():
    while pulse:
        GPIO.output(pulse_pin, GPIO.HIGH)
        sleep(1)
        GPIO.output(pulse_pin, GPIO.LOW)
        sleep(1)
    if not pulse:
        logging.error('Pulse Stopped')


def cpu_temp():
    while True:
        temp = cpu.temperature
        with open("cpu_temp.csv", "a") as log:
            log.write("{0},{1}\n".format(strftime("%Y-%m-%d %H:%M:%S"), str(temp)))
        sleep(900)


def port_select():
    if port_count == 5:
        cmd = 'sudo wvdial --config=/etc/wvdial_5.conf'
        port = '/dev/ttyUSB3'
        return cmd, port
    elif port_count == 6:
        cmd = 'sudo wvdial --config=/etc/wvdial_6.conf'
        port = '/dev/ttyUSB4'
        return cmd, port
    elif port_count == 7:
        cmd = 'sudo wvdial --config=/etc/wvdial_7.conf'
        port = '/dev/ttyUSB5'
        return cmd, port
    else:
        logging.error('Desired Port Not Found')

def enable_sim():
    sleep(2)
    command = port_select()
    try:
        ser = serial.Serial(command[1], baudrate=115200, timeout=5)
        ser.write(bytes("AT+cmee=2\r\n", 'utf-8'))
        sleep(1)
        ser.write(bytes("AT#CEERURC=1\r\n", 'utf-8'))
        sleep(1)
        ser.write(bytes("AT#REJER=1\r\n", 'utf-8'))
        sleep(1)
        ser.write(bytes("AT#CEERNETEXT=1\r\n", 'utf-8'))
        sleep(1)
        ser.write(bytes("AT#SIMDET=1\r\n", 'utf-8'))
        sleep(1)
        ser.write(bytes('AT+CGDCONT=1,"IPV4V6","Jiociot2\r\n"', 'utf-8'))
        sleep(1)
        ser.close()
    except Exception as ex:
        logging.error(ex)

def usb_eth_enable():
    sleep(2)
    command = port_select()
    try:
        ser = serial.Serial(command[1], baudrate=115200, timeout=5)
        ser.write(bytes("AT#USBCFG=1\r\n", 'utf-8'))
        sleep(1)
        ser.close()
    except Exception as ex:
        logging.error(ex)

def dial_rndis():
    sleep(1)
    command = port_select()
    try:
        ser = serial.Serial(command[1], baudrate=115200, timeout=5)
        ser.write(bytes("AT#RNDIS=1,0\r\n", 'utf-8'))
        sleep(1)
        serCount = ser.inWaiting()
        response = str(ser.read(serCount))
        ser.close()
        return response
    except Exception as ex:
        logging.error(ex)

def dial_internet():
    dial_count = 0
    usb_eth_enable()
    sleep(40)
    enable_sim()
    sleep(15)
    try:
        rndis_response = dial_rndis()
        #logging.error(rndis_response)
    except:
        dial_count = dial_count + 1
        if dial_count == 6:
            logging.error('Not able to dial Internet')
            dial_count = 0

def check_modem():
    logging.error('Device Powered ON')
    modem_count = 0
    global pulse
    pulse = True
    global mqtt_connect_count
    mqtt_connect_count = True
    global port_count
    port_count = 0
    ping_count = 0
    while True:
        ports = list(serial.tools.list_ports.comports())
        required_ports = list()
        port_count = 0
        for p in ports:
            if fnmatch.fnmatch(p.name, "ttyUSB*") is True:
                port_count = port_count + 1
        if port_count >= 5:
            modem_count = 0
            sleep(60)
            internet_count = 0
            for i in range(7):
                url = ['test-broker.crystalpower.in']
                for u in url:
                    try:
                        subprocess.check_output(['ping', '-6', '-c', '2', u])
                        ping_count += 1
                    except subprocess.CalledProcessError as e:
                        logging.error(e)
                        ping_count = 0
                if ping_count > 0:
                    if mqtt_connect_count:
                        os.system('sudo systemctl restart crystalTransport.service')
                        mqtt_connect_count = False
                    sleep(60)
                    internet_count = 0
                else:
                    internet_count = internet_count + 1
                    mqtt_connect_count = True
                    if internet_count == 6:
                        pulse = False
                        internet_count = 0
                        logging.error('Internet Down')
                        try:
                            os.system('sudo -S shutdown -h now')
                        except Exception as e:
                            logging.error(e)
                            os.system('sudo -S shutdown -h now')
                    sleep(60)
        else:
            modem_count = modem_count + 1
            if modem_count == 10:
                logging.error('Modem not detected')
                modem_count = 0
                pulse = False
                os.system('sudo -S shutdown -h now')
            sleep(30)

t = Thread(target=check_modem)
t.start()
t = Thread(target=main_sense)
t.start()
t = Thread(target=pulse_gen)
t.start()
# t = Thread(target=cpu_temp)
# t.start()
#t = Thread(target=enable_sim)
#t.start()
t = Thread(target=dial_internet)
t.start()
