#!/usr/bin/env python3
import tornado.httpserver
import tornado.websocket
import tornado.concurrent
import tornado.ioloop
import tornado.web
import tornado.gen
from tornado import gen
import threading
import asyncio
import json
import socket
import numpy as np
import imutils
import copy
import time
from time import strftime
import datetime
import cv2
import os
import uuid
import sys
clients = {}

bytes = b''
myPort = 9090
conTimeout =1 * 10 * 1000 #10 Sec
lock = threading.Lock()
connectedDevices = set()
connectedDevicesControl = set()
frameSz = [    
    ['FRAMESIZE_96X96',  96,  96],
    ['FRAMESIZE_QQVGA',  160,120],
    ['FRAMESIZE_QCIF',   176,144],
    ['FRAMESIZE_HQVGA',  240,176],
    ['FRAMESIZE_240X240',240,240],
    ['FRAMESIZE_QVGA',   320,240],
    ['FRAMESIZE_CIF',    400,296],
    ['FRAMESIZE_HVGA',   480,320],
    ['FRAMESIZE_VGA',    640,480],
    ['FRAMESIZE_SVGA',   800,600],
    ['FRAMESIZE_XGA',    1024,768],
    ['FRAMESIZE_HD',     1280,720],
    ['FRAMESIZE_SXGA',   1280,1024],
    ['FRAMESIZE_UXGA',   1600,1200]
]
              
def update(base, new):
    if isinstance(base, dict):
        for k, v in new.items():
            if k in base:
                base[k] = v
        return {k: update(v, new) for k, v in base.items()}
    else:
        return base
                  
class WSControlHandler(tornado.websocket.WebSocketHandler):
    def __init__(self, *args, **kwargs):
        super(WSControlHandler, self).__init__(*args, **kwargs)
        self.executor = tornado.concurrent.futures.ThreadPoolExecutor(max_workers=4)

    def open(self):
        print('Control connection from ip: ', self.request.remote_ip)
        connectedDevicesControl.add(self)
        self.write_message("Connected to: " + socket.gethostname());
        
    def _close_on_timeout(self):
        if self.ws_connection:
            print('Connection timed out with host: ', self.request.remote_ip )
            self.close()

    def on_message(self, message):
        message=message.replace('\n','')
        try:
            j = json.loads(message)
            id = j['id']
            message = j['cmd']
            WSHandler.send_message(id, message)
            print(id + ' < ' + message) #  ip: ' + self.request.remote_ip)
        except Exception as e:
            print('Not a valid message: ', message, e )
    
    @classmethod
    def send_message(self, message=""):
        #print("Broadcasting msg:", message)
        for client in connectedDevicesControl:
            client.write_message(message);            
                
        return True;

    def on_close(self):
        print('Control connection closed ip: ' + self.request.remote_ip)
        connectedDevicesControl.remove(self)

    def check_origin(self, origin):
        return True
    
    
class WSHandler(tornado.websocket.WebSocketHandler):
    def __init__(self, *args, **kwargs):
        super(WSHandler, self).__init__(*args, **kwargs)
        self.outputFrame = None
        self.frame = None
        self.id = None
        self.executor = tornado.concurrent.futures.ThreadPoolExecutor(max_workers=4)
        self.client_id = str(uuid.uuid4())
            
    def process_frames(self):
        if self.frame is None:
            return
        #frame = imutils.rotate_bound(self.frame.copy(), 0)
        frame = self.frame.copy()
        img_h, img_w = frame.shape[:2]
        tmS = strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.tms) )
        tmS = tmS + ' ('+str(self.fps)+")"
        cv2.putText(frame, self.id, (20, 20), cv2.FONT_HERSHEY_COMPLEX_SMALL , .5, (255, 255, 255), 1)
        textsize = cv2.getTextSize(tmS, cv2.FONT_HERSHEY_COMPLEX_SMALL, .5, 2)[0]
        cv2.putText(frame, tmS, (img_w - (textsize[0] + 20), 20), cv2.FONT_HERSHEY_COMPLEX_SMALL , .5, (255, 255, 255), 1)
        #print('t:',self.tmr );
        if self.tmr is not None:
            if time.time() - self.tmr > 2:  
                self.tmr = None
            cv2.putText(frame, self.ctrlMsg, (20, img_h - 20), cv2.FONT_HERSHEY_COMPLEX_SMALL , .5, (255, 255, 255), 1)            
        
        if self.motion is not None:            
            if time.time() - self.motion > 2:
                self.motion = None
            cv2.rectangle(frame, pt1=[1,1], pt2=[img_w-2,img_h-2],color=(0, 0, 255), thickness=2)

        (flag, encodedImage) = cv2.imencode(".jpg", frame)        
        
        if not flag: #Ensure the frame was successfully encoded
            print("Error decoding")
            return
        self.outputFrame = encodedImage.tobytes()

    def open(self):
        #print('New connection from ip: ',self.request.remote_ip)
        connectedDevices.add(self)
        clients[self.client_id] = self
        self.write_message("Connected to: " + socket.gethostname());
        self.timeout = tornado.ioloop.IOLoop.instance().add_timeout(
        datetime.timedelta(milliseconds=conTimeout), self._close_on_timeout)
        
    def _close_on_timeout(self):
        if self.ws_connection:
            if self.id is not None:
                print('Connection timed out with host: ' + self.id )
                msg = {}
                msg['timestamp']=str(time.time())
                msg['self.id'] = self.id;
                msg['msg'] = 'conTimeout'
                WSControlHandler.send_message(json.dumps(msg))   
            self.close()

    def on_message(self, message):
        #print( self)
        # Remove previous timeout, if one exists.
        if self.timeout:
            tornado.ioloop.IOLoop.instance().remove_timeout(self.timeout)
            self.timeout = None
        
        if message[0]=='#': #Text messages
            #print(self.client_id)
            msg = message.split("|")
            tmS=""
            if len(msg)==2:
                tm = int(msg[0].replace('#',''))
                tmS = strftime('%Y-%m-%d %H:%M:%S>', time.localtime(tm) )                    
                try:
                    info = json.loads(msg[1])
                except:                    
                    info = None
                    
                if info is not None:  #Json first info                  
                    if self.id is None:
                        if info['hostName']:
                            self.id = info['hostName']
                        self.info = info
                        self.motion = None
                        self.tmr = None
                        self.ctrlMsg = None
                        self.frames = 0
                        self.frames_timestamp = time.time()  
                        self.fps = 0
                        print(tmS,'Connected: '+ self.id+ ', ip: '+ self.request.remote_ip, ', framesize:', frameSz[int(self.info['framesize'])][1],'x',frameSz[int(self.info['framesize'])][2] )
                    else :
                        #print('Update info :', json.dumps(info,indent=2, separators=(" ", " = ")).replace('"', "").replace('}','').replace('{',''))                        
                        clients[self.client_id].info.update(info)
                    #info = self.info
                    info['timestamp']=str(tm)
                    info['self.id'] = self.id;
                    info['msg'] = 'info'
                    WSControlHandler.send_message(json.dumps(info))    
                else: #Plain text
                    print(tmS,'Received msg:', msg[1],' from:',self.id);
                    #Broadcase message
                    info = json.loads("{}");
                    info['timestamp']=str(tm)
                    info['self.id'] = self.id;
                    info['msg'] = msg[1];
                    WSControlHandler.send_message(json.dumps(info))
                    if msg[1].startswith("MotionStart"):
                        self.motion = tm
                    elif msg[1].startswith("MotionEnd"):
                        self.motion = None

                    self.tmr = time.time() 
                    self.ctrlMsg = msg[1]
            else: #Unformated text
                print(tmS,'Received text:', message,' from:',self.id);
        else : #raw image data
            try: 
                #Extract timestamp
                self.tms = int(message[-10:]);
                message = message[:-10]            
                self.frame = cv2.imdecode(np.frombuffer(
                    message, dtype=np.uint8), cv2.IMREAD_COLOR)
                self.frames = self.frames + 1
                if time.time() - self.frames_timestamp > 1:
                    print("Rcv Fps: ", self.frames,' from:',self.id)
                    self.fps = self.frames
                    self.frames=0;
                    self.frames_timestamp = time.time()      
                   
                self.process_frames()
            except Exception as e:
                print("Bad frame data from:",self.id, e)
        self.timeout = tornado.ioloop.IOLoop.instance().add_timeout(
                datetime.timedelta(milliseconds=conTimeout), self._close_on_timeout)
        
    
    @classmethod
    def send_message(self, id='all',  message=""):
        print(id + " > " + message)
        for client in connectedDevices:
            if id=='all' or client.id == id:
                client.write_message(message);
                if client.id == id:                
                    break;
                
        return True;

    def on_close(self):
        # Remove previous timeout, if one exists.
        if self.timeout:
            tornado.ioloop.IOLoop.instance().remove_timeout(self.timeout)
            self.timeout = None
            
        if self.id is not None:
            print('Connection closed with host: ' + self.id + ', ip: ' + self.request.remote_ip)
        # self.stopEvent.set()
        connectedDevices.remove(self)
        clients.pop(self.client_id, None)

    def check_origin(self, origin):
        return True
            
class StreamHandler(tornado.web.RequestHandler):
    @tornado.gen.coroutine
    def get(self, slug):
        ioloop = tornado.ioloop.IOLoop.current()

        self.set_header('Cache-Control', 'no-store, no-cache, must-revalidate, pre-check=0, post-check=0, max-age=0')
        self.set_header('Pragma', 'no-cache')
        self.set_header('Content-Type', 'multipart/x-mixed-replace;boundary=--jpgboundary')
        self.set_header('Connection', 'close')

        self.served_image_timestamp = time.time()
        self.served_fps_timestamp = time.time()
        my_boundary = "--jpgboundary"
        client = None
        for c in connectedDevices:
            if c.id == slug:
                #print('s:',slug)
                client = c
                #client.image_frames=0;
                break
        while client is not None:
            jpgData = client.outputFrame
            if jpgData is None:
                try:
                    sz = int(client.info['framesize']);
                    w = frameSz[sz][1];
                    h = frameSz[sz][2];
                    #print("Empty frame from: " +  client.id, ', w:', w,', h: ',h)
                    
                    image  = np.zeros((h, w, 3), np.uint8)
                    cv2.putText(image, 'No video', (40, 60), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 1)
                    # encoding picture to jpeg
                    ret, jpeg = cv2.imencode('.jpg', image)
                    jpgData = jpeg.tobytes()
                except:
                    jpgData = None        
                #continue
            interval = 0.1
            if jpgData and self.served_image_timestamp + interval < time.time():
                self.write(my_boundary)
                self.write("Content-type: image/jpeg\r\n")
                self.write("Content-length: %s\r\n\r\n" % len(jpgData))
                self.write(jpgData)                
                '''
                client.image_frames = client.image_frames  + 1
                if time.time() - self.served_fps_timestamp > 1:
                   print("Fps: ", client.image_frames)
                   client.image_frames=0;
                   self.served_fps_timestamp = time.time()
                   '''                   
                yield tornado.gen.Task(self.flush)
                #yield self.flush()
            else:
                yield tornado.gen.Task(ioloop.add_timeout, ioloop.time() + interval)

class SetParamsHandler(tornado.web.RequestHandler):
    @tornado.web.asynchronous
    def post(self):
        # print self.request.body
        presets = self.get_argument('presets').replace('\r\n', '\n')
        #print(presets)
        presetsFile = os.path.sep.join([os.path.dirname(__file__), "templates", "presets.txt"])        
        # try to save presets
        try:
            with open(presetsFile, 'w+') as f:
                f.write(presets)
            
            print("Saved presets:  " + str(len(presets)) + ' bytes')
            self.write({'resp': 'ok'})
        except Exception as e:
            self.write({'resp': 'error'})
            self.flush()
            self.finish()


class TemplateHandler(tornado.web.RequestHandler):
    def get(self):
        #remote_ip = self.request.headers.get("X-Real-IP") or \
        #    self.request.headers.get("X-Forwarded-For") or \
        #    self.request.remote_ip
        #print('Remoteip :', remote_ip);
            
        #print(presets)
        if len(connectedDevices) == 0:
            clientsNum  = 0
            deviceIds   = []
            deviceIps   = []
            deviceInfos = []
        else:
            try:
                clientsNum = len(connectedDevices) 
                deviceIds = [d.id for d in connectedDevices]
                deviceIps = [d.request.remote_ip for d in connectedDevices]            
                deviceInfos = [json.dumps(d.info) for d in connectedDevices]
            except Exception as e:
                deviceIds = []
                deviceInfos = []
        
        videoUrl = "http://" + (socket.gethostname()) + ":" + str(myPort) + "/video_feed/"
        self.render(os.path.sep.join(
            [os.path.dirname(__file__), "templates", "index.html"]), clientsNum=clientsNum, url=videoUrl, deviceIds=deviceIds, deviceIps=deviceIps, deviceInfos=deviceInfos)


application = tornado.web.Application([
    (r'/video_feed/([^/]+)', StreamHandler),
    (r'/control', SetParamsHandler),            
    (r'/ws', WSHandler),
    (r'/wsc', WSControlHandler),
    (r'/', TemplateHandler),
    (r'/(?:image)/(.*)', tornado.web.StaticFileHandler, {'path': './image'}),
    (r'/(?:css)/(.*)', tornado.web.StaticFileHandler, {'path': './css'}),
    (r'/(?:js)/(.*)', tornado.web.StaticFileHandler, {'path': './js'}),
    (r'/(?:templates)/(.*)', tornado.web.StaticFileHandler, {'path': './templates'})
])


if __name__ == "__main__":
    http_server = tornado.httpserver.HTTPServer(application)
    http_server.listen(myPort)
    myIP = socket.gethostbyname(socket.gethostname())
    #myIP = '10.0.0.8'    
    print('Python: ', sys.version)
    print('tornado: ',tornado.version)
    print('numpy: ',np.__version__)
    print('*** Websocket Server Started at %s, %s:%s ***' % (socket.gethostname(), myIP,myPort))

    tornado.ioloop.IOLoop.current().start()
