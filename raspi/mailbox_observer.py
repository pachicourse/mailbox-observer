from mode import device
import wiringpi
import json
import os
import subprocess
import requests
import hmac
import hashlib
import base64
import shutil
from time import gmtime, strftime
import logging

NC_API_KEY = os.environ.get('NC_API_KEY')
NC_SECRET_KEY = os.environ.get('NC_SECRET_KEY').encode('utf-8')
DEVICE_ID = os.environ.get('DH_DEVICE_ID')
DEVICE_API_KEY = os.environ.get('DH_DEVICE_API_KEY')
DEVICE_ENDPOINT = os.environ.get('DH_ENDPOINT')
OS_BUCKET_NAME = os.environ.get('OS_BUCKET_NAME')
OS_ENDPOINT = os.environ.get('OS_ENDPOINT')

TILT_PIN = 21

picture_url = './image.jpg'
mode_device = device.Device()

def on_message(ws, message):
    json_message = json.loads(message)

    #check command value
    if json_message['action'] == 'take_picture': 
        try:
            picture_process()
        except Exception as e:
            logging.error('take_picture is failed ', e)

def take_picture(pic_url): 
    commands = ['sudo', 'fswebcam', pic_url]
    subprocess.call(commands)
        
def upload_picture(api_key, secret_key, endpoint, \
                   obj_path, content_type, bucket_name, file_name):
    obj = open(obj_path, 'rb')
    obj_size = str(os.path.getsize(obj_path))
    time_stamp = strftime("%a, %d %b %Y %H:%M:%S %Z", gmtime())
    string_to_sign = '\n'.join(['PUT', '', content_type, time_stamp, \
                     '/%s/%s' % (bucket_name, file_name)])
    h = hmac.new(secret_key, b'', hashlib.sha1)
    h.update(string_to_sign.encode('utf-8'))
    calculated_signature = base64.b64encode(h.digest())
    auth = 'AWS %s:%s' % (api_key, calculated_signature.decode('utf-8')) 
    r = requests.put('https://' + bucket_name + '.' + endpoint + '/' + file_name, \
                     obj,
                     headers={'Content-length':obj_size, \
                              'Content-Type':content_type, \
                              'Date':time_stamp,
                              'Authorization':auth})
    logging.info('upload_picture response' + str(r))

def remove_picture(pic_url):
    commands = ['sudo', 'rm', pic_url]
    subprocess.call(commands)

def picture_process():
    try:
        take_picture(picture_url)
        upload_picture(NC_API_KEY, NC_SECRET_KEY, OS_ENDPOINT, \
                       picture_url, 'imege/jpeg', OS_BUCKET_NAME, \
                       'image.jpg')
        remove_picture(picture_url)
        mode_device.trigger_event('Posted', {'tilt':0})
    except Exception as e:
        logging.error('take_picture is failed ', e)
        
if __name__ == '__main__':
    #Set logging
    logging.basicConfig(filename='raspi.log', level=logging.INFO, \
                        format='%(asctime)s %(message)s')
    
    #Set endpoint  
    mode_device.set_device_keys(DEVICE_ID, DEVICE_API_KEY)
    mode_device.set_api_host(DEVICE_ENDPOINT)

    #Set gpio
    wiringpi.wiringPiSetupGpio()
    wiringpi.pinMode(TILT_PIN, 0) # set GPIO 21 to input.

    #Monitoring tilt switch
    wiringpi.wiringPiISR(TILT_PIN, wiringpi.INT_EDGE_FALLING, \
                         picture_process)

    #Listen commands and override callback method
    mode_device.set_on_message(on_message)
    mode_device.listen_commands()
