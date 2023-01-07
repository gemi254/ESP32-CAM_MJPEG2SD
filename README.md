
This is a modified version of ESP32-CAM_MJPEG2SD, providing a **surveillance system** from multiple esp32-cam cameras, using a web socket server on a **remote host** over the **internet**.

Added a **web-socket multi-client server** (websockets_stream_server.py) written in Python, that can be run on a remote host (Windows/Linux), allowing ep32 camera clients to connect and transmit their video feeds. ESP32-CAM_MJPEG2SD acts as a websocket client, making remote connections to the server, allowing video streams to be transmitted over the internet without any port/firewall restrictions. Multiple esp32-camera clients can be connected simultaneously on the python server and all remote streams can be viewed on a **single control page**. 

From this page you can control each camera's **parameters remotely** allowing to change frame rate, motion detection, or set it's **resolution**. You can type in the `Remote query` input box a text command and press enter to send this command to this camera. For example fps=10 will set the remote camera's fps to 10. Alternative you can type a text command to the `Remote query for all clients` edit box and the command will be transmitted to all connected cameras. Multiple comma separated commands can also be entered allowing detailed setup of each camera client. An editable list box with user's **sets of commands** is available so setup combinations can be stored and recalled later.

On the remote host you will need to have **python 3** installed with some additional packages, and a free tcp port to make the connections (default is 9090). See /python_ backend/install.txt for information how to install stream server on the remote host. 

After installing server configure each ESP32-CAM client. Navigate to camera interface `Websocket settings` > `Remote server` edit box and enter the address of your server:port (i.e. ws://myserver.org:9090/ws). Now press the `Camera control` > `Remote streaming` > `On` to enable remote connection and transmit video feed.

On the remote server visit http://myserver.org:9090 to see all the videos streams from remote clients connected. Each video frame contains a **timestamp** of the local camera time, that is displayed as `video clock` with `hostname` at the top of the video feed. If **motion detection** is enabled on ESP32-CAM_MJPEG2SD, a motion message will be transmitted to the server and a **red box** will rendered on that video feed. 

Remote cameras also transmit other **information messages** like changes in the setup (framesize, lamp, fps) to the stream server and will be displayed in the bottom of each video stream. On mouse over each camera's `Remote query` input box, a text log will be displayed with all messages send / receive and on mouse over stream image an information text will be displayed as well.


# ESP32-CAM_MJPEG2SD

Visit https://github.com/s60sc/ESP32-CAM_MJPEG2SD for more details
