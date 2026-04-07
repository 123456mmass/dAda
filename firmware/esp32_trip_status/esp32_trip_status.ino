#include <Arduino.h>
#include <WiFi.h>
#include <WebServer.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>

// ESP32-S3 Dev Module common I2C pins. Change these only if your wiring is different.
constexpr int I2C_SDA_PIN = 8;
constexpr int I2C_SCL_PIN = 9;
constexpr uint8_t LCD_COLS = 20;
constexpr uint8_t LCD_ROWS = 4;

const char* AP_SSID = "RelayDisplay-ESP";
const char* AP_PASSWORD = "relay1234";

struct RelaySnapshot {
  String state = "BOOT";
  String family = "UNKNOWN";
  int tap = 0;
  String phases = "-";
  String idiff = "0.00,0.00,0.00";
  String threshold = "0.00,0.00,0.00";
  int tripCount = 0;
};

RelaySnapshot snapshot;
WebServer server(80);
LiquidCrystal_I2C* lcd = nullptr;
uint8_t lcdAddress = 0;
String testMessage;
unsigned long testMessageUntilMs = 0;

String trimText(String value) {
  value.trim();
  return value;
}

String fitLine(String value) {
  if (value.length() > LCD_COLS) {
    return value.substring(0, LCD_COLS);
  }
  while (value.length() < LCD_COLS) {
    value += " ";
  }
  return value;
}

String firstCsvValue(const String& csv) {
  int comma = csv.indexOf(',');
  if (comma < 0) {
    return csv;
  }
  return csv.substring(0, comma);
}

void lcdPrintAt(uint8_t col, uint8_t row, const String& message) {
  if (!lcd) {
    return;
  }
  lcd->setCursor(col, row);
  lcd->print(fitLine(message));
}

void renderBootScreen(const String& line1, const String& line2, const String& line3, const String& line4) {
  if (!lcd) {
    return;
  }
  lcd->clear();
  lcdPrintAt(0, 0, line1);
  lcdPrintAt(0, 1, line2);
  lcdPrintAt(0, 2, line3);
  lcdPrintAt(0, 3, line4);
}

void renderStatusToLcd() {
  if (!lcd) {
    return;
  }

  lcd->clear();

  if (!testMessage.isEmpty() && millis() < testMessageUntilMs) {
    lcdPrintAt(0, 0, "TEST MESSAGE");
    lcdPrintAt(0, 1, testMessage);
    lcdPrintAt(0, 2, "SSID: " + String(AP_SSID));
    lcdPrintAt(0, 3, WiFi.softAPIP().toString());
    return;
  }

  String header = snapshot.state + " " + snapshot.family + " T" + String(snapshot.tap);
  String phasesLine = "PH: " + snapshot.phases + " CNT:" + String(snapshot.tripCount);
  String idiffLine = "IdfA: " + firstCsvValue(snapshot.idiff);
  String thrLine = "ThrA: " + firstCsvValue(snapshot.threshold);

  lcdPrintAt(0, 0, header);
  lcdPrintAt(0, 1, phasesLine);
  lcdPrintAt(0, 2, idiffLine);
  lcdPrintAt(0, 3, thrLine);
}

void renderStatusToSerial() {
  Serial.println();
  Serial.println("=== ESP RELAY DISPLAY ===");
  Serial.printf("STATE   : %s\n", snapshot.state.c_str());
  Serial.printf("FAMILY  : %s\n", snapshot.family.c_str());
  Serial.printf("TAP     : %d\n", snapshot.tap);
  Serial.printf("PHASES  : %s\n", snapshot.phases.c_str());
  Serial.printf("IDIFF   : %s\n", snapshot.idiff.c_str());
  Serial.printf("THRESH  : %s\n", snapshot.threshold.c_str());
  Serial.printf("COUNT   : %d\n", snapshot.tripCount);
  Serial.printf("IP      : %s\n", WiFi.softAPIP().toString().c_str());
  Serial.println("=========================");
}

bool initLcd() {
  const uint8_t candidates[] = {0x27, 0x3F};
  for (uint8_t address : candidates) {
    Wire.beginTransmission(address);
    if (Wire.endTransmission() == 0) {
      lcdAddress = address;
      lcd = new LiquidCrystal_I2C(lcdAddress, LCD_COLS, LCD_ROWS);
      lcd->init();
      lcd->backlight();
      return true;
    }
  }
  return false;
}

void handleRoot() {
  String body;
  body.reserve(256);
  body += "ESP Relay Display\n";
  body += "ssid=" + String(AP_SSID) + "\n";
  body += "ip=" + WiFi.softAPIP().toString() + "\n";
  body += "lcd=" + String(lcd ? "ready" : "not-found") + "\n";
  body += "state=" + snapshot.state + "\n";
  server.send(200, "text/plain", body);
}

void handleStatus() {
  snapshot.state = trimText(server.arg("state"));
  if (snapshot.state.isEmpty()) {
    snapshot.state = "UNKNOWN";
  }
  snapshot.family = trimText(server.arg("family"));
  if (snapshot.family.isEmpty()) {
    snapshot.family = "UNKNOWN";
  }
  snapshot.tap = server.arg("tap").toInt();
  snapshot.phases = trimText(server.arg("phases"));
  if (snapshot.phases.isEmpty()) {
    snapshot.phases = "-";
  }
  snapshot.idiff = trimText(server.arg("idiff"));
  if (snapshot.idiff.isEmpty()) {
    snapshot.idiff = "0.00,0.00,0.00";
  }
  snapshot.threshold = trimText(server.arg("threshold"));
  if (snapshot.threshold.isEmpty()) {
    snapshot.threshold = "0.00,0.00,0.00";
  }
  snapshot.tripCount = server.arg("count").toInt();
  testMessage = "";
  testMessageUntilMs = 0;

  renderStatusToLcd();
  renderStatusToSerial();
  server.send(200, "text/plain", "OK");
}

void handleHello() {
  String message = trimText(server.arg("message"));
  if (message.isEmpty()) {
    message = "HELLO";
  }
  testMessage = message;
  testMessageUntilMs = millis() + 15000;
  renderStatusToLcd();
  Serial.printf("HELLO test: %s\n", message.c_str());
  server.send(200, "text/plain", "HELLO SHOWN");
}

void setup() {
  Serial.begin(115200);
  delay(1000);

  Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN);
  bool lcdReady = initLcd();

  WiFi.mode(WIFI_AP);
  bool apReady = WiFi.softAP(AP_SSID, AP_PASSWORD);

  server.on("/", HTTP_GET, handleRoot);
  server.on("/status", HTTP_GET, handleStatus);
  server.on("/hello", HTTP_GET, handleHello);
  server.begin();

  Serial.println("ESP32 relay display ready");
  Serial.printf("AP status: %s\n", apReady ? "OK" : "FAILED");
  Serial.printf("AP SSID : %s\n", AP_SSID);
  Serial.printf("AP PASS : %s\n", AP_PASSWORD);
  Serial.printf("AP IP   : %s\n", WiFi.softAPIP().toString().c_str());
  Serial.printf("LCD     : %s\n", lcdReady ? "READY" : "NOT FOUND");
  if (lcdReady) {
    Serial.printf("LCD I2C : 0x%02X\n", lcdAddress);
  }

  renderBootScreen(
    "RelayDisplay-ESP",
    String(apReady ? "AP OK " : "AP FAIL ") + WiFi.softAPIP().toString(),
    lcdReady ? "LCD READY" : "LCD NOT FOUND",
    "WAITING STATUS"
  );
}

void loop() {
  server.handleClient();
}
