from bs4 import BeautifulSoup
from datetime import datetime
from time import sleep

import libtorrent as lt
import paho.mqtt.client as mqtt
#from threading import Thread

import os
import requests
import json
import threading
import logging

topic = "/animesub"
client = None

class MQTTCtrl:
    client = None

    def __init__(self, server, port):
        self.client = mqtt.Client()
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.connect(server, port, 60)

        tmqtt = threading.Thread(target=self.client.loop_forever, args=[])
        tmqtt.start()

    def on_connect(self, client, userdata, flags, rc):
        print("CONNECTED")
        print("Connected with result code: ", str(rc))
       
        client.subscribe(topic)
        print("subscribing to topic : " + topic)

    def on_message(self, client, userdata, message):
        print("Data requested " + str(message.payload))

    def get_info(self):
        return self.client
 
# Faking a official browser
headers = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/50.0.2661.75 Safari/537.36",
    "X-Requested-With": "XMLHttpRequest"
}
 
class ReadRss:
    def __init__(self, rss_url, headers):
        self.url = rss_url
        self.headers = headers

        try:
            self.r = requests.get(rss_url, headers=self.headers, )
            self.status_code = self.r.status_code
        except Exception as e:
            print('Error fetching the URL: ', rss_url)
            print(e)
            quit()

        try:    
            self.soup = BeautifulSoup(self.r.text, 'lxml')
        except Exception as e:
            print('Could not parse the xml: ', self.url)
            print(e)
            quit()
        
        self.articles = self.soup.findAll('item')
        self.articles_dicts = [{'title':a.find('title').text,'link':a.link.next_sibling.replace('\n','').replace('\t',''),'description':a.find('description').text,'pubdate':a.find('pubdate').text} for a in self.articles]
        self.urls = [d['link'] for d in self.articles_dicts if 'link' in d]
        self.titles = [d['title'] for d in self.articles_dicts if 'title' in d]
        self.descriptions = [d['description'] for d in self.articles_dicts if 'description' in d]
        self.pub_dates = [d['pubdate'] for d in self.articles_dicts if 'pubdate' in d]

    def get_torrent_file(self, url, torrdir):
        if not url:
            return None

        fname = url.split('/')
        
        if len(fname[-1]) == 0:
            return None

        print (fname[-1])

        r = requests.get(url, allow_redirects=True)
        if r.status_code != 200:
            return None
                
        open(torrdir + fname[-1], 'wb').write(r.content)

        return (torrdir + fname[-1])

def torrent():
    sess = None
    torrentf = "/files/"
    torrentdata = "/torrents/"

    try:
        with open("config.json") as configfile:
            cfgdata = json.load(configfile)
            if not cfgdata["fileinit"]:
                print ("Invalid json or invalid field.")
            else:
                
                feed = ReadRss(cfgdata["rsssource"], headers)
                mymqtt = MQTTCtrl(cfgdata["mqttserv"], cfgdata["mqttport"])

                while(True):
                    cnt = 0 # Waiting for best form to use.
                    for i in feed.titles:
                        for j in cfgdata["q_default"]:
                            if i.find(j) != -1:
                                for z in cfgdata["keywords"]:
                                    if i.find(z) != -1:
                                        if sess is None:
                                            sess = lt.session()

                                        name = feed.get_torrent_file(url=feed.urls[cnt], torrdir=os.getcwd() + torrentf)

                                        if name is not None:

                                            ti = lt.torrent_info(name)

                                            torrentfiledir = os.getcwd() + torrentdata
                                            handle = sess.add_torrent({'ti': ti, 'save_path': torrentfiledir})

                                            cliifo = mymqtt.get_info()
                                            ret = cliifo.publish("/animepub", "Downloading:" + str(feed.titles[cnt]))

                                            print ("Downloading metadata...")
                                            while (not handle.has_metadata()):
                                                sleep(2)
                                            print ("Got metadata, starting torrent download...")
                                            while (handle.status().state != lt.torrent_status.seeding):
                                                s = handle.status()
                                                state_str = ['queued', 'checking', 'downloading metadata', 'downloading', 'finished', 'seeding', 'allocating']
                                                print ("%.2f%% complete (down: %.1f kb/s up: %.1f kB/s peers: %d) %s" % (s.progress * 100, s.download_rate / 1000, s.upload_rate / 1000, s.num_peers, state_str[s.state]))
                                                sleep(5)  
                                        else:
                                            pass
                        cnt = cnt + 1
                    print ("All selected animes were downloaded.")    
                    sleep(cfgdata["intervupd"]) 
    except ValueError:
        # Any field is invalid.
        print (" Invalid json or invalid field.")
    except FileNotFoundError:
        print (" Configfile not found. Creating a new one.")
        with open("config.json", "w") as configfile:
            cfgdata = {
            "fileinit": datetime.now().strftime("%Y-%m-%d %H:%M"), 
            "q_default" : ["480p", "540p"], 
            "intervupd": 1800,
            "mqttserv" : "beaglebone.local",
            "mqttport" : 1883,
            "rsssource" : "https://nyaa.si/?page=rss&q=%5BSubsPlease%5D&c=1_2&f=0",
            "keywords" : ["Deatte", "Fumetsu", "Academia", "Mairimashita", "Shitara", "Tsuki"] }
            json.dump(cfgdata, configfile)
    sleep(5)

if __name__ == '__main__':
    ttorr = threading.Thread(target=torrent, args=[])
    ttorr.start()

    while(True):
        sleep(10)
    