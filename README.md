This is a modified version from https://github.com/s60sc/ESP32-CAM_MJPEG2SD
* Added local sdcard logging (/log.txt). Set remote_log_mode on file utils.cpp to 0,1 to set debug mode.
  Uncomment //remote_log_init(); on line 53 on file ESP32-CAM_MJPEG2SD to enable wifi connection debugging (remote_log_mode 1 - sdcard file only)
	You can use view-source:http://[camera ip]/file?log.txt to view the log generated.
* Added minimize/maximize button for full screen video playback. 
* Fixed set station static IP from config.
* Fixed remote telnet debug.
* compile with arduino-esp32 stable release is v1.0.6
* format the sd card if mount failed 
* Remote logging/debugging via telnet on camera ip and port 443.
* Automatic ftp upload new recordings on motion detection.
* Check if file exists on upload a folder and ignore it. Incremental  upload
* Fixed save / restore camera settings on boot
* Reload page on reboot

![image1](extras/screenshot.png)

# ESP32-CAM_MJPEG2SD
ESP32 Camera extension to record JPEGs to SD card as MJPEG files and playback to browser. 

Files uploaded by FTP are optionally converted to AVI format to allow recordings to replay at correct frame rate on media players.

## Purpose
The MJPEG format contains the original JPEG images but displays them as a video. MJPEG playback is not inherently rate controlled, but the app attempts to play back at the MJPEG recording rate. MJPEG files can also be played on video apps or converted into rate controlled AVI or MKV files etc.

Saving a set of JPEGs as a single file is faster than as individual files and is easier to manage, particularly for small image sizes. Actual rate depends on quality and size of SD card and complexity and quality of images. A no-name 4GB SDHC labelled as Class 6 was 3 times slower than a genuine Sandisk 4GB SDHC Class 2. The following recording rates were achieved on a freshly formatted Sandisk 4GB SDHC Class 2 using SD_MMC 1 line mode on a AI Thinker OV2640 board, set to maximum JPEG quality and highest clock rate.

Frame Size | OV2640 camera max fps | mjpeg2sd max fps | Detection time ms
------------ | ------------- | ------------- | -------------
96X96 | 50 | 45 |  15
QQVGA | 50 | 45 |  20
QCIF  | 50 | 45 |  30
HQVGA | 50 | 45 |  40
240X240 | 50 | 45 |  55
QVGA | 50 | 40 |  70
CIF | 50 | 40 | 110
HGVA | 50 | 40 | 130
VGA | 25 | 20 |  80
SVGA | 25 | 20 | 120
XGA | 6.25 | 5 | 180
HD | 6.25 | 5 | 220
SXGA | 6.25 | 5 | 300
UXGA | 6.25 | 5 | 450

## Design

The ESP32 Cam module has 4MB of pSRAM which is used to buffer the camera frames and the construction of the MJPEG file to minimise the number of SD file writes, and optimise the writes by aligning them with the SD card sector size. For playback the MJPEG is read from SD into a multiple sector sized buffer, and sent to the browser as timed individual frames.

The SD card can be used in either __MMC 1 line__ mode (default) or __MMC 4 line__ mode. The __MMC 1 line__ mode is practically as fast as __MMC 4 line__ and frees up pin 4 (connected to onboard Lamp), and pin 12 which can be used for eg a PIR.  

The MJPEG files are named using a date time format __YYYYMMDD_HHMMSS__, with added frame size, recording rate, duration and frame count, eg __20200130_201015_VGA_15_60_900.mjpeg__, and stored in a per day folder __YYYYMMDD__.  
The ESP32 time is set from an NTP server. 

## Installation and Use

Note: Needs to be compiled with latest `arduino-esp32` Stable Release v1.0.6.

Download files into the Arduino IDE sketch location, removing `-master` from the folder name.  
The included sketch `ESP32-CAM_MJPEG2SD.ino` is derived from the `CameraWebServer.ino` example sketch included in the Arduino ESP32 library. 
Additional code has been added to the original file `app_httpd.cpp` to handle the extra browser options, and an additional file`mjpeg2sd.cpp` contains the SD handling code. The web page content in `camera_index.h` has been updated to include additional functions. 
The face detection code has been removed to reduce the sketch size to allow OTA updates.

To set the recording parameters, additional options are provided on the camera index page, where:
* `Frame Rate` is the required frames per second
* `Min Frames` is the minimum number of frames to be captured or the file is deleted
* `Verbose` if checked outputs additional logging to the serial monitor

An MJPEG recording is generated by holding a given pin high (kept low by internal pulldown when released).  
The pin to use is:
* pin 12 when in 1 line mode
* pin 33 when in 4 line mode

An MJPEG recording can also be generated by the camera itself detecting motion as given in the __Motion detection by Camera__ section below.

If recording occurs whilst also live streaming to browser, the frame rate will be slower. 

To play back a recording, select the file using __Select folder / file__ on the browser to select the day folder then the required MJPEG file.
After selecting the MJPEG file, press __Start Stream__ button to playback the recording. 
The recorded playback rate can be changed during replay by changing the __FPS__ value. 
After playback finished, press __Stop Stream__ button. 
If a recording is started during a playback, playback will stop.

The following functions are provided by [@gemi254](https://github.com/gemi254):

* Entire folders or files within folders can be deleted by selecting the required file or folder from the drop down list then pressing the __Delete__ button and confirming.

* Entire folders or files within folders can be uploaded to a remote server via FTP by selecting the required file or folder from the drop down list then pressing the __FTP Upload__ button.

* The FTP, Wifi, and other parameters need to be defined in file `myConfig.h`, and can also be modified via the browser under __Other Settings__.

* Check internet connection and automatically reconnect if needed on power loss.

* Added mdns name services in order to use `http://[Host Name]` instead of ip address

* Delete or ftp upload and delete oldest folder when card free space is running out.  
  See `minCardFreeSpace` and `freeSpaceMode` in `mjpeg2sd.cpp`


Additional ancilliary functions:

* Enable Over The Air (OTA) updates - see `ota.cpp`
* Add temperature sensor - see `ds18b20.cpp`
* Add analog microphone support - see `avi.cpp`

Browser functions only tested on Chrome.


## Motion detection by Camera

An MJPEG recording can also be generated by the camera itself detecting motion using the `motionDetect.cpp` file.  
JPEG images of any size are retrieved from the camera and 1 in N images are sampled on the fly for movement by decoding them to very small grayscale bitmap images which are compared to the previous sample. The small sizes provide smoothing to remove artefacts and reduce processing time.

For movement detection a high sample rate of 1 in 2 is used. When movement has been detected, the rate for checking for movement stop is reduced to 1 in 10 so that the JPEGs can be captured with only a small overhead. The __Detection time ms__ table shows typical time in millis to decode and analyse a frame retrieved from the OV2640 camera.

To enable motion detection by camera, in `mjpeg2sd.cpp` set `#define USE_MOTION true`

Additional options are provided on the camera index page, where:
* `Motion Sensitivity` sets a threshold for movement detection, higher is more sensitive.
* `Show Motion` if enabled and the __Start Stream__ button pressed, shows images of how movement is detected for calibration purposes. Gray pixels show movement, which turn to black if the motion threshold is reached.

![image1](extras/motion.png)

The `motionDetect.cpp` file contains additional documented monitoring parameters that can be modified. 
