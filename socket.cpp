//#include "myConfig.h"
#include "appGlobals.h"
#include "esp_websocket_client.h"
#include "esp_event.h"

char websocket_ip[16] = "";         //Websocket server ip to connect.  
char websocket_port[5] = "";         //Websocket server port to connect.  
bool bConnected = false;
bool doRemoteStream = false;         //Will activate on wifi connect!
bool remoteStreamEnabled = false;    //Enable/Disable streaming to a websocket server
bool remoteStreamPaused = false;
bool remoteStreamInProgress = false;

esp_websocket_client_handle_t sclient;
static TaskHandle_t socketTaskHandle = NULL;
bool bConvert = false;
static int taskDelay = 0;
static camera_fb_t * fb = NULL;
static size_t fb_len = 0;
static size_t _jpg_buf_len = 0;
static uint8_t * _jpg_buf = NULL;

static uint32_t frames = 0, frameTime, statsTime = 0, frameTimeTtl = 0;
static char remoteQuery[128] = "";

/** \brief Opcode according to RFC 6455*/
typedef enum {
  WS_OP_CON = 0x0,        /*!< Continuation Frame*/
  WS_OP_TXT = 0x1,        /*!< Text Frame*/
  WS_OP_BIN = 0x2,        /*!< Binary Frame*/
  WS_OP_CLS = 0x8,        /*!< Connection Close Frame*/
  WS_OP_PIN = 0x9,        /*!< Ping Frame*/
  WS_OP_PON = 0xa         /*!< Pong Frame*/
} WS_OPCODES;

void freeCamera() {
  esp_camera_fb_return(fb);
  fb = NULL;
  xSemaphoreGive(frameMutex);
}
void socketSendToServerData(const char *data) {
  if (!esp_websocket_client_is_connected(sclient)) return;
  struct tm timeinfo;
  if (!getLocalTime(&timeinfo)) return;
  int n = strlen(data) + 20;
  char buff[n];
  sprintf(buff, "#%lu|%s", mktime(&timeinfo), data);
  esp_websocket_client_send_text(sclient, buff, strlen(buff), portMAX_DELAY);
}
void checkForRemoteQuerry() {
  //Execure remote querry dbgVerbose=1;framesize=7;fps=1
  if(strlen(remoteQuery) > 0) {
    char* query = strtok(remoteQuery, ";");
    while (query != NULL) {
        char* value = strchr(query, '=');
        if (value != NULL) {
          *value = 0; // split remoteQuery into 2 strings, first is key name
          value++; // second is value
          LOG_DBG("Execute q: %s v: %s", query, value);
          //Extra handling
          if (!strcmp(query, "socketFps")) { //Socket frames per second
             if(atoi(value)<=0) taskDelay =0;
             else taskDelay = (int)(1000.0f / atof(value));
             LOG_INF("Setting task delay: %i ms",taskDelay);
          }else if (!strcmp(query, "pause")) { //Pause socket stream but listen commands
             remoteStreamPaused = atoi(value);
             LOG_INF("Pause stream: %i", remoteStreamPaused);
          }else if (!strcmp(query, "reset")) { //Reboot
             doRestart("Socket remote restart");             
          }else if (!strcmp(query, "socketJpg")) { //Socket frames to jpeg conversion
             bConvert = atoi(value);
             LOG_INF("Convert to jpg: %i", bConvert);
          }else{  
             //Block other tasks from accessing the camera
             xSemaphoreTake(frameMutex, portMAX_DELAY);
             if (!strcmp(query, "fps")) setFPS(atoi(value));
             else if (!strcmp(query, "framesize"))  setFPSlookup(fsizePtr);
             updateStatus(query, value);
             xSemaphoreGive(frameMutex);
          }          
        } else { //No params command
          LOG_DBG("Execute cmd: %s", query);
          if (!strcmp(query, "status")) {
            buildJsonString(false);
            socketSendToServerData(jsonBuff);
          } else if (!strcmp(query, "status?q")) {
            buildJsonString(true);
            socketSendToServerData(jsonBuff);
          }
        }
        query = strtok(NULL, ";");
    }
    remoteQuery[0] = '\0';
  }  
}

static void socketTask(void* parameter) {
  remoteStreamInProgress = false;
  while (remoteStreamEnabled) {
    //LOG_DBG("Waiting for signal..");
    ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
    //LOG_DBG("Wake..");
    if (esp_websocket_client_is_connected(sclient)) {
      remoteStreamInProgress = true;
      //Check if server sends a remote command
      checkForRemoteQuerry();
      //Stream is paused
      if(remoteStreamPaused){
        LOG_DBG("paused");
        socketSendToServer("paused");  
        vTaskDelay(2000 / portTICK_RATE_MS);
        xTaskNotifyGive(socketTaskHandle); 
        continue;
      }
      //Block other tasks from accessing the camera
      xSemaphoreTake(frameMutex, portMAX_DELAY);
      if (statsTime == 0) statsTime = millis();
      frameTime = millis();
      //Capture frame
      fb = esp_camera_fb_get();
      if (!fb) {
        LOG_ERR("Capture failed");
        freeCamera();
        //vTaskDelay(500 / portTICK_RATE_MS);
      } else {      
        struct tm timeinfo;
        getLocalTime(&timeinfo);
        char buff[20];
        sprintf(buff, "%lu", mktime(&timeinfo));
        int tmSz = strlen(buff);
        //LOG_INF("%s|%i",buff, tmSz);
        //Store frame in a buffer to be trasmited        
        uint8_t *frBuffer = (uint8_t*)ps_malloc( fb->len + tmSz); // buffer frame to store frame
        if (!frBuffer) {
          LOG_ERR("Memory allocation failed");
          freeCamera();
          vTaskDelay(500 / portTICK_RATE_MS);
        } else { //Copy buffer so it can be transmited
          
          //Convert to jpg if needed
          if(bConvert && fb->width > 400 && fb->format != PIXFORMAT_JPEG){
              bool jpeg_converted = frame2jpg(fb, 80, &_jpg_buf, &_jpg_buf_len);
              if(jpeg_converted){
                memcpy(frBuffer, _jpg_buf, _jpg_buf_len);
                fb_len = _jpg_buf_len;
              }else{
                LOG_ERR("JPEG compression failed");              
                memcpy(frBuffer, fb->buf, fb->len);
                fb_len = fb->len;
              }
          }else{//Already jpg
              memcpy(frBuffer, fb->buf, fb->len);
              fb_len = fb->len;
          }
          freeCamera();
          size_t buffSize = fb_len  + tmSz;          
          //Add current timestamp at the end of the buffer
          memcpy(frBuffer + fb_len , buff, tmSz);
          int dataLen = esp_websocket_client_send_bin(sclient, (const char*) frBuffer, buffSize, portMAX_DELAY);
          free(frBuffer);
          if(dataLen <0){
            LOG_ERR("Send failed, toSend %i, send:%i",buffSize, dataLen);
            //vTaskDelay(500 / portTICK_RATE_MS);
          }
          ++frames;
          frameTimeTtl += millis() - frameTime;
          if (millis() - statsTime > 1000) {
            //LOG_DBG("%3.1f fps, %u frames (%3.1f Kb) avg: %u ms", (1000.0f / (frameTimeTtl / frames)),frames, (buffSize / 1024.0), frameTimeTtl / frames);
            LOG_DBG("%u frames (avg: %3.1f Kb, in %u ms)", frames, (buffSize / 1024.0), frameTimeTtl / frames);
            frameTimeTtl = 0;
            frames = 0;
            statsTime = millis();
          }          
        }
        if(taskDelay > 0 ) vTaskDelay(taskDelay / portTICK_RATE_MS);
      }
    }else{ //Disconnected      
      LOG_INF("Disconnected wait..");
      vTaskDelay(2000 / portTICK_RATE_MS);
    }
    xTaskNotifyGive(socketTaskHandle);    
  }
  LOG_INF("exiting..");
  remoteStreamInProgress = false;
  vTaskDelete(NULL);
}

void socketSendToServer(const char* msg, ...)
{
  char buff[256];
  va_list argptr;
  va_start(argptr, msg);
  vsnprintf(buff, 256, msg, argptr);
  //Serial.println(buff);
  socketSendToServerData(buff);
}

void startSocketStream(void) {
  LOG_INF("Sending websocket headers");
  for (int tries = 3; tries >= 0; tries--) {
    if (esp_websocket_client_is_connected(sclient)) {
      buildJsonString(false);
      //Send header
      socketSendToServerData(jsonBuff);
      //Resume
      LOG_DBG("Resuming websocket thread..");
      xTaskNotifyGive(socketTaskHandle);
      tries = -1;
    } else { //Wait for connection
      LOG_ERR("Connect to ws://%s:%s/ws FAILED", websocket_ip, websocket_port);
      vTaskDelay(1000 / portTICK_RATE_MS);
    }
  }
}

static void websocket_event_handler(void *handler_args, esp_event_base_t base, int32_t event_id, void *event_data)
{
  esp_websocket_event_data_t *data = (esp_websocket_event_data_t *)event_data;
  switch (event_id) {
    case WEBSOCKET_EVENT_CONNECTED:
      bConnected = true;
      LOG_DBG("WEBSOCKET_EVENT_CONNECTED");
      startSocketStream();
      break;
    case WEBSOCKET_EVENT_DISCONNECTED:
      bConnected = false;
      LOG_DBG("WEBSOCKET_EVENT_DISCONNECTED");
      break;
    case WEBSOCKET_EVENT_DATA:
      //LOG_INF("WEBSOCKET_EVENT_DATA Received opcode=%d", data->op_code);
      switch (data->op_code) {
        case WS_OP_CON:
          LOG_DBG("Received Continuation message");
          break;
        case WS_OP_PIN:
          LOG_DBG("Received Ping message");
          break;
        case WS_OP_PON:
          LOG_DBG("Received Pong message");
          break;
        case WS_OP_TXT:
        {
          LOG_DBG("Received Text: %.*s", data->data_len, (char *)data->data_ptr);
          if (strlen(remoteQuery) == 0) sprintf(remoteQuery, "%.*s", data->data_len, (char *)data->data_ptr);                  
          break;
        }
        case WS_OP_CLS:
          bConnected = false;
          LOG_DBG("Received Close frame with code=%d", 256 * data->data_ptr[0] + data->data_ptr[1]);
          break;
        default:
          LOG_DBG("Received unknown msg with code=%d", 256 * data->data_ptr[0] + data->data_ptr[1]);
          break;

      }
      //if(data->payload_len>0) LOG_WRN("Total payload length=%d, data_len=%d, current payload offset=%d", data->payload_len, data->data_len, data->payload_offset);
      break;
    case WEBSOCKET_EVENT_ERROR:
      LOG_DBG("WEBSOCKET_EVENT_ERROR");
      break;
  }
}
void startWebsocketClient(void)
{
  if (remoteStreamEnabled || remoteStreamInProgress) {
    LOG_INF("Streaming is running.. Exiting");
    return;
  }
  if (WiFi.status() != WL_CONNECTED) {
    doRemoteStream = true;
    LOG_INF("Wifi disconnected.. Activate on connect");
    return;
  }
  doRemoteStream = false;
  esp_websocket_client_config_t websocket_cfg = {};
  String websocket_uri("ws://" + String(websocket_ip) + ":" + String(websocket_port) + "/ws");
  
  websocket_cfg.uri = websocket_uri.c_str();
  websocket_cfg.buffer_size = (10 * 1024);
  /*
  websocket_cfg.disable_auto_reconnect = false;  
  websocket_cfg.keep_alive_enable = true;
  websocket_cfg.keep_alive_interval = 2;  
  websocket_cfg.reconnect_timeout_ms = 5000;
  */

  LOG_INF("Connect to %s...", websocket_cfg.uri);
  sclient = esp_websocket_client_init(&websocket_cfg);
  esp_websocket_register_events(sclient, WEBSOCKET_EVENT_ANY, websocket_event_handler, (void *)sclient);

  esp_websocket_client_start(sclient);
  //Create a socket stream task
  remoteStreamEnabled = true;
  BaseType_t xReturned = xTaskCreate(&socketTask, "socketTask", 4096 * 2, NULL, 1, &socketTaskHandle);
  LOG_INF("Created task: %d", xReturned );
}

void stopWebsocketClient(void)
{
  LOG_INF("Stopping..%u", socketTaskHandle);
  if (!remoteStreamEnabled) return;
  remoteStreamPaused = false;
  remoteStreamEnabled = false;
  if ( socketTaskHandle != NULL ) {
    LOG_DBG("Unlock task..");
    xTaskNotifyGive(socketTaskHandle); //Unblock task
    vTaskDelay(1500 / portTICK_RATE_MS);
    LOG_DBG("Deleted task..?");
  }
  LOG_DBG("Closing..");
  esp_websocket_client_close(sclient, portMAX_DELAY);
  esp_websocket_client_destroy(sclient);
  LOG_INF("Stopped");
  remoteStreamInProgress = false;
  socketTaskHandle = NULL;
}
