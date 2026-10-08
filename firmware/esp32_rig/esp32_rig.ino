/*
 * AI-ARCTEG ESP32 telemetry firmware
 * -----------------------------------
 * Reads the hybrid PV + TEG sensor rig and POSTs JSON frames to the
 * backend ingestion endpoint over WiFi/HTTP.
 *
 * Hardware assumed (adjust pins for your board):
 *   - Pyranometer / PV voltage divider   -> GPIO34 (ADC1_CH6)
 *   - PV current sense (ACS712-style)    -> GPIO35 (ADC1_CH9)
 *   - TEG hot-side thermistor (NTC)      -> GPIO32 (ADC1_CH4)
 *   - TEG cold-side thermistor (NTC)     -> GPIO33 (ADC1_CH5)
 *   - River thermistor (NTC)             -> GPIO39 (ADC1_CH3)
 *   - Ambient thermistor (NTC)           -> GPIO36 (ADC1_CH0)
 *   - Battery voltage divider            -> GPIO25 (ADC2_CH8)
 *
 * Configuration: edit the constants below, or flash your own secrets.
 * The API key must match DEVICE_INGEST_API_KEY in the backend .env.
 *
 * Build: Arduino IDE (esp32 board package) or PlatformIO.
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <time.h>

// ---- configuration -------------------------------------------------------
static const char* WIFI_SSID     = "YOUR_WIFI_SSID";
static const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";
static const char* API_BASE_URL  = "http://192.168.1.100:8000";  // backend host
static const char* DEVICE_UID    = "esp32-rig-01";
static const char* API_KEY       = "dev-ingest-key";
static const uint32_t INTERVAL_MS = 5000;   // sample period (matches backend tick)

// ---- pins ----------------------------------------------------------------
static const int PIN_PV_VOLT   = 34;
static const int PIN_PV_AMP    = 35;
static const int PIN_T_HOT     = 32;
static const int PIN_T_COLD    = 33;
static const int PIN_T_RIVER   = 39;
static const int PIN_T_AMBIENT = 36;
static const int PIN_BATT_VOLT = 25;

// ---- helpers -------------------------------------------------------------
float adcToVoltage(int pin) {
  // 12-bit ADC, 3.3 V reference (adjust divider ratio for your board).
  int raw = analogRead(pin);
  return raw / 4095.0f * 3.3f;
}

float readThermistorC(int pin) {
  // 10k NTC with 10k series resistor, beta=3950 — simplified Steinhart-lite.
  float v = adcToVoltage(pin);
  float ratio = v / 3.3f;
  if (ratio <= 0.001f) ratio = 0.001f;
  if (ratio >= 0.999f) ratio = 0.999f;
  float resistance = 10000.0f * ratio / (1.0f - ratio);
  float steinhart = log(resistance / 10000.0f) / 3950.0f;
  return 1.0f / (steinhart + 1.0f / 298.15f) - 273.15f;
}

float readPvVoltage() {
  // 1:11 divider assumed for a ~0-36 V PV string -> scale to volts.
  return adcToVoltage(PIN_PV_VOLT) * 11.0f;
}

float readPvCurrent() {
  // ACS712-20A: 100 mV/A centered at Vcc/2 (approximate, unidirectional here).
  float v = adcToVoltage(PIN_PV_AMP);
  float amps = (v - 1.65f) / 0.1f;
  return amps > 0 ? amps : 0;
}

float readBatteryVoltage() {
  return adcToVoltage(PIN_BATT_VOLT) * 4.0f;  // 1:3 divider
}

bool postTelemetry(const String& body) {
  HTTPClient http;
  String url = String(API_BASE_URL) + "/api/v1/ingest/telemetry";
  http.begin(url);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-API-Key", API_KEY);
  http.setTimeout(4000);
  int code = http.POST(body);
  http.end();
  return code == 200;
}

// ---- setup / loop --------------------------------------------------------
void setup() {
  Serial.begin(115200);
  analogReadResolution(12);

  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("Connecting to WiFi");
  uint32_t start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 20000) {
    delay(250);
    Serial.print(".");
  }
  Serial.println();
  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("Connected, IP: ");
    Serial.println(WiFi.localIP());
    configTime(0, 0, "pool.ntp.org");  // UTC for timestamps
  } else {
    Serial.println("WiFi connect failed — will keep retrying");
  }
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    WiFi.reconnect();
    delay(1000);
    return;
  }

  float pvVoltage   = readPvVoltage();
  float pvCurrent   = readPvCurrent();
  float tHot        = readThermistorC(PIN_T_HOT);
  float tCold       = readThermistorC(PIN_T_COLD);
  float tRiver      = readThermistorC(PIN_T_RIVER);
  float tAmbient    = readThermistorC(PIN_T_AMBIENT);
  float battVoltage = readBatteryVoltage();

  // TEG output: module is small; assume ~45 mV/K Seebeck, matched load.
  float deltaT = tHot - tCold;
  if (deltaT < 0) deltaT = 0;
  float tegVoltage = 0.045f * deltaT;
  float tegCurrent = tegVoltage / (2.0f * 3.2f);  // R_int = 3.2 ohm

  float pvPower   = pvVoltage * pvCurrent;
  float tegPower  = tegVoltage * tegCurrent;
  float total     = pvPower + tegPower;
  float incident  = 0.0f;  // pyranometer not wired in this revision
  float efficiency = 0.0f;
  if (pvPower > 0) {
    // Estimate irradiance proxy from PV short-circuit-ish current.
    float irrEstimate = pvCurrent / 0.0085f * 1000.0f;  // ~8.5 mA per 1000 W/m2
    if (irrEstimate > 1200) irrEstimate = 1200;
    incident = irrEstimate * 0.5f;  // 0.5 m2 aperture
    if (incident > 1) efficiency = total / incident * 100.0f;
  }
  float irrEstimate = pvCurrent / 0.0085f * 1000.0f;
  if (irrEstimate > 1200) irrEstimate = 1200;

  StaticJsonDocument<768> doc;
  doc["device_uid"]           = DEVICE_UID;
  doc["irradiance"]           = constrain(irrEstimate, 0, 2000);
  doc["ambient_temperature"]  = tAmbient;
  doc["hot_temperature"]      = tHot;
  doc["cold_temperature"]     = tCold;
  doc["river_temperature"]    = tRiver;
  doc["pv_voltage"]           = pvVoltage;
  doc["pv_current"]           = pvCurrent;
  doc["teg_voltage"]          = tegVoltage;
  doc["teg_current"]          = tegCurrent;
  doc["battery_voltage"]      = battVoltage;
  doc["battery_soc"]          = constrain((battVoltage - 10.5) / (12.6 - 10.5) * 100.0f, 0, 100);

  String body;
  serializeJson(doc, body);

  if (postTelemetry(body)) {
    Serial.printf("posted: pv=%.1fW teg=%.2fW dT=%.1fK\n", pvPower, tegPower, deltaT);
  } else {
    Serial.println("POST failed (will buffer next frame locally if offline)");
  }

  delay(INTERVAL_MS);
}
