#!/usr/bin/env python
# -*- coding: utf8 -*-

import RPi.GPIO as GPIO
import MFRC522
import signal
import requests
import time
import os
import base64
import sqlite3


# Setup localcache database if it doesn't exist
conn = sqlite3.connect('localcache.db')
c = conn.cursor()
c.execute('CREATE TABLE IF NOT EXISTS handshakes(tagid text, date text, status text)')
conn.commit()
conn.close()

# REST request function
def sendHandshake(tagid):
    url = ''
    username = ''
    password = ''
    # Load config
    if os.path.isfile('config/conf.cnf'):
        with open('config/conf.cnf', 'r') as conf:
            url = conf.readline().rstrip()
            username = conf.readline().rstrip()
            password = conf.readline().rstrip()
            conf.close()

    authHash = username + ':' + password
    authHash = authHash.encode('utf-8')
    authHash = base64.b64encode(authHash)
    querystring = {"_format":"json"}
    payload = {
                  "type": [
                      {
                          "target_id": "handshake",
                          "target_type": "node_type",
                      }
                  ],
                  "title": [
                      {
                          "value": "From Pi for user " + username
                      }
                  ],
                  "field_object_id": [
                      {
                          "value": tagid
                      }
                  ]
              }
    headers = {
        'content-type': "application/json",
        'authorization': "Basic " + authHash,
        'cache-control': "no-cache",
    }

    try:
        response = requests.request("POST", url, json=payload, headers=headers, params=querystring)
        response.raise_for_status()
        print response.status_code
        return True
    except requests.exceptions.HTTPError as err:
        print "Error: %s" % response.status_code
        return False

# Begin continuous loop

continue_reading = True

# Capture SIGINT for cleanup when the script is aborted
def end_read(signal,frame):
    global continue_reading
    print "Ctrl+C captured, ending read."
    continue_reading = False
    GPIO.cleanup()

# Hook the SIGINT
signal.signal(signal.SIGINT, end_read)

# Create an object of the class MFRC522
MIFAREReader = MFRC522.MFRC522()

# Welcome message
print "Quack Quack"
print "Press Ctrl-C to stop."

# This loop keeps checking for chips. If one is near it will get the UID and authenticate
while continue_reading:
    
    # Scan for cards    
    (status,TagType) = MIFAREReader.MFRC522_Request(MIFAREReader.PICC_REQIDL)

    # Get the UID of the card
    (status,uid) = MIFAREReader.MFRC522_Anticoll()

    # If we have the UID, continue
    if status == MIFAREReader.MI_OK:

        # Select the scanned tag
        MIFAREReader.MFRC522_SelectTag(uid)

        # Read sector 6 from the card and store this 'handshake'
        sector6 = MIFAREReader.MFRC522_Read(6)
        if sector6:
            tagid = ''

            # Specifically remove some characters.
            for char in sector6:
                if char > 0 and char <= 125:
                    ascii = chr(char).encode(encoding='ascii',errors='ignore')
                    tagid = tagid + ascii

            tagid = tagid[1:]
            tagid = tagid.strip(' \n\r')

            # Caching system for handshakes.
            # Check for existing entries in the localcache file
            matches = False

            conn = sqlite3.connect('localcache.db')
            c = conn.cursor()
            t = (tagid,)
            c.execute('SELECT * FROM handshakes WHERE tagid = ?', t)
            matches = c.fetchone()

            if matches:
                print "existing tagid found in localcache.csv: " + tagid
            else:
                print "no existing tagid in cache for: " + tagid + ". We will add one now."
                c.execute('INSERT INTO handshakes VALUES (?, ?, ?)', (tagid, time.ctime(), '0'))
                conn.commit()
            conn.close()

            # Delay card reading if card was read successfully
            time.sleep(1)

    # No read occurred, continue to process the cache file though.
    # Attempt to make REST requests if we have anything in the cache file.

    # Process cache file:
    matches = False
    sending = []
    conn = sqlite3.connect('localcache.db')
    c = conn.cursor()
    status = ('0',)
    c.execute('SELECT * FROM handshakes WHERE status = ?', status)
    matches = c.fetchone()
    if matches:

        # Update this line to be a status of 1
        tagid = matches[0]
        print "going to update db record for tagid: " + repr(tagid)
        c.execute('''UPDATE handshakes SET status = '1' WHERE status = ? AND tagid = ?''', ('0', tagid))
        conn.commit()
        r = sendHandshake(matches[0]);

        if r:
            # Success! Set status to 2
            c.execute('''UPDATE handshakes SET status = '2' WHERE status = ? AND tagid = ?''', ('1', tagid))
            conn.commit()
        else:
            # Set status to 0 because it failed
            c.execute('''UPDATE handshakes SET status = '0' WHERE status = ? AND tagid = ?''', ('1', tagid))
            conn.commit()
            # Avoid dos'ing the API
            time.sleep(1 )
    conn.close()