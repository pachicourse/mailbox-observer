# -*- coding: utf-8 -*-

import os
import smtplib
import requests
from email.mime.text import MIMEText
from flask import Flask, request, render_template, make_response
from flask import jsonify, session, redirect, url_for
from flask.ext.api import status
from time import gmtime, strftime
import hmac
import hashlib
import base64
import shutil
import logging
import json
from configparser import ConfigParser
from mode import application

#for ESS
ADDRESS = os.environ.get('MAIL_ADDRESS')
SMTP_ID = os.environ.get('ESS_SMTP_ID')
SMTP_PASSWORD = os.environ.get('ESS_SMTP_PASS')
SMTP_HOST = os.environ.get('SMTP_HOST')
SMTP_PORT = 587
#for Authentication
WEBHOOK_URL = os.environ.get('WEBHOOK_URL').encode('utf-8')
WEBHOOK_KEY = os.environ.get('WEBHOOK_KEY').encode('utf-8')
NC_API_KEY = os.environ.get('NC_API_KEY')
NC_SECRET_KEY = os.environ.get('NC_SECRET_KEY').encode('utf-8')
#for Object Storage
OS_ENDPOINT = os.environ.get('OS_ENDPOINT')
OS_BUCKET_NAME = os.environ.get('OS_BUCKET_NAME')
#for IoT Device Hub
DH_ENDPOINT = os.environ.get('DH_ENDPOINT')
DH_USER_API_KEY = os.environ.get('DH_USER_API_KEY')
DH_DEVICE_ID = os.environ.get('DH_DEVICE_ID')

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)

@app.before_request
def before_request():
    if request.path == '/api/events':
        return
    #Already logged
    if session.get('username') is not None:
        return
    #Accessing to login page
    if request.path == '/login':
        return
    #Not logged in yet.
    return redirect('/login')

@app.route('/login', methods=['GET', 'POST'])
def login():
    #User logged in
    if request.method == 'POST' and _is_account_valid():
        session['username'] = request.form['username']
        return redirect(url_for('index'))

    #return to login page
    return render_template('login.html')

def _is_account_valid():
    #Read user info from config.ini
    logging.basicConfig(filename='server.log',level=logging.INFO, \
                        format='%(asctime)s %(message)s')
    config = ConfigParser()
    config.read('./config.ini')
    username = request.form.get('username')
    password = request.form.get('password')
    if username == config['user']['name'] and password == config['user']['password']:
        return True
    logging.info('Failed login.')
    return False

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('login'))

@app.route('/api/events', methods=['POST'])
def check_event(): 
    logging.basicConfig(filename='server.log',level=logging.INFO, \
                        format='%(asctime)s %(message)s')
    event_type = request.json["eventType"]
    logging.info(event_type)

    #Authentication
    if not is_authenticated(request.data, request.headers):
        logging.error('Authentication Failed')
        return 'UNAUTHORIZED', status.HTTP_401_UNAUTHORIZED
    
    if event_type == "Posted":
        body_text = 'Chech your mailbox!'
        subject_text = 'You got a postal matter.'
        r = post_to_ess(SMTP_HOST, SMTP_PORT, SMTP_ID, SMTP_PASSWORD, \
                        ADDRESS, ADDRESS, text=body_text, subject=subject_text)
        return r

@app.route('/api/command/take_picture', methods=['POST'])
def send_take_picture_command():
    mode_app = application.Application()
    mode_app.set_api_host(DH_ENDPOINT)
    mode_app.set_user_key(DH_USER_API_KEY)
    mode_app.trigger_command(DH_DEVICE_ID, 'take_picture', {'value':1})
    return redirect('/') 

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/image.jpg')
def display_picture(): 
    logging.basicConfig(filename='server.log',level=logging.INFO, \
                        format='%(asctime)s %(message)s')
    file_name = 'image.jpg'
    time_stamp = strftime("%a, %d %b %Y %H:%M:%S %Z", gmtime())
    string_to_sign = 'GET' + '\n' \
                   + '\n' \
                   + 'application/octet-stream' + '\n' \
                   + time_stamp + '\n' \
                   + '/%s/%s' % (OS_BUCKET_NAME, file_name)
    h = hmac.new(NC_SECRET_KEY, b'', hashlib.sha1)
    h.update(string_to_sign.encode('utf-8'))
    calculated_signature = base64.b64encode(h.digest())
    auth = 'AWS %s:%s' % (NC_API_KEY, calculated_signature.decode('utf-8'))
    url = 'https://' + OS_BUCKET_NAME + '.' + OS_ENDPOINT + '/' + file_name
    r = requests.get(url, stream=True, \
                     headers={'Content-Type':'application/octet-stream', \
                              'Date':time_stamp, \
                              'Authorization':auth}) 
    logging.info(r)
    return make_response(r.content)

def is_authenticated(req_body, req_headers):
    h = hmac.new(WEBHOOK_KEY, b'', hashlib.sha256)
    h.update(WEBHOOK_URL + req_body)
    calculated_signature = h.hexdigest()
    return calculated_signature == req_headers['X-Mode-Signature']

def post_to_ess(host, port, smtp_id, smtp_pass, from_address, to_address, \
                text='text', subject='subject'):
    
    logging.basicConfig(filename='server.log',level=logging.INFO, \
                        format='%(asctime)s %(message)s')

    #Make message
    msg = MIMEText(text)
    msg['Subject'] = subject
    msg['From'] = from_address
    msg['To'] = to_address
    
    #Post to ESS
    try:
        smtp = smtplib.SMTP(host, port)
    except Exception as e:
        logging.error('SMTP construct error.', e)
        return 'SERVICE_UNAVAILABLE', status.HTTP_503_SERVICE_UNAVAILABLE
    
    try:    
        smtp.ehlo()
        smtp.starttls()
        smtp.login(smtp_id, smtp_pass)
        smtp.sendmail(from_address, to_address, msg.as_string())
    except Exception as e:
        logging.error('Send mail process error.', e)
        return 'SERVICE_UNAVAILABLE', status.HTTP_503_SERVICE_UNAVAILABLE
    finally:
        smtp.quit()

    logging.info('sent the mail.')
    return 'OK', status.HTTP_200_OK

if __name__ == '__main__':
    app.run(host="0.0.0.0", debug=False, threaded=True)
