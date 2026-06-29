/* ============================================================================
 *  b1_bringup.ino  —  SailFrames B1 hardware bring-up / self-test
 * ----------------------------------------------------------------------------
 *  A standalone diagnostic sketch for a fresh-from-fab B1 board. Unlike the
 *  production firmware, it NEVER blocks/halts — in particular it does NOT halt
 *  when the microSD is missing or unreadable. It probes every B1 peripheral,
 *  prints PASS/FAIL with detail over serial @115200, and drops into an
 *  interactive menu so you can re-test one subsystem at a time while you
 *  reflow/probe the board.
 *
 *  Pins are the authoritative B1 map (edge-b/hardware/B1_PIN_MAP.md) —
 *  identical to E1 firmware where it matters, so a passing SD/I2C here means
 *  the production firmware will read them too.
 *
 *  Build (same toolchain as production):
 *    arduino-cli compile --fqbn esp32:esp32:esp32:PartitionScheme=default \
 *      edge-b/firmware/b1_bringup
 *    arduino-cli upload  --fqbn esp32:esp32:esp32 -p <PORT> edge-b/firmware/b1_bringup
 *  (ESP32 core 3.3.7. TFT test needs the project's TFT_eSPI User_Setup.h; if
 *   you don't have it configured, set TEST_TFT 0 below and it still builds.)
 *
 *  Menu (type a letter + Enter @115200):
 *    a = run all tests     sd = retry SD       i = I2C scan      b = battery
 *    g = GNSS UART dump     l = LED cycle       q = latch read    t = TFT redraw
 *    m = continuous monitor (Ctrl-C / any key to stop)           h = help
 * ========================================================================== */

#include <Wire.h>
#include <SPI.h>
#include <SD.h>

#define TEST_TFT 1
#if TEST_TFT
  #include <TFT_eSPI.h>
  TFT_eSPI tft;
#endif

// ---------------- B1 pin map (edge-b/hardware/B1_PIN_MAP.md) ----------------
// I2C (BNO085)
#define PIN_SDA    21
#define PIN_SCL    22
#define BNO_ADDR   0x4B   // GY-BNO08X, ADO pulled high on-board
#define BNO_ALT    0x4A   // Adafruit-style fallback
#define DPS_ADDR   0x77
// microSD on HSPI (must match production: 14/13/35/27)
#define SD_CLK     14
#define SD_MOSI    13
#define SD_MISO    35     // input-only pin
#define SD_CS      27
// GNSS LC29HEA on UART2
#define GNSS_RX    16     // ESP32 RX  <- GNSS TXD1
#define GNSS_TX    17     // ESP32 TX  -> GNSS RXD1
#define GNSS_PPS   39     // input-only
// Battery + power latch
#define PIN_VBAT   34     // ADC1_6, 100K/100K divider on VBAT
// v0.13 Qi-power: GPIO19 = PWR_HOLD. OUTPUT, drives /LATCH_Q via R28(0R).
// HIGH = boost latched on (survives lift-off pad); LOW/hi-Z = off (R_PD pulls
// LATCH_Q low). Must be driven HIGH as the FIRST GPIO op in setup(). On the pad
// the MCU also lives on the D7/Qi rail, so the latch only matters once lifted.
#define PIN_PWR_HOLD 19
// Status LEDs (active LOW, 220R)
#define LED_RED    33     // D4
#define LED_WHITE  32     // D5
#define LED_CYAN   26     // D6
// TFT backlight (B1 = GPIO25)
#define TFT_BL     25

SPIClass sdSPI(HSPI);
bool g_sdOK = false;

// ----------------------------------------------------------------------------
static void line() { Serial.println(F("--------------------------------------------------")); }

static void banner() {
  Serial.println();
  line();
  Serial.println(F("  SailFrames B1 BRING-UP self-test (non-blocking)"));
  Serial.print  (F("  reset reason: ")); Serial.println((int)esp_reset_reason());
  Serial.print  (F("  free heap: ")); Serial.println(ESP.getFreeHeap());
  line();
}

// ---------------- Battery + latch ----------------
static float readBattV() {
  // analogReadMilliVolts is factory-calibrated on ESP32 core 3.x.
  uint32_t mv = 0;
  for (int i = 0; i < 8; i++) mv += analogReadMilliVolts(PIN_VBAT);
  mv /= 8;
  return (mv / 1000.0f) * 2.0f;   // undo the 100K/100K divider
}

static void testBattery() {
  float v = readBattV();
  Serial.printf("[BATT] GPIO34 -> %.2f V  %s\n", v,
                (v > 3.0f && v < 4.4f) ? "OK (plausible LiPo)" :
                (v < 0.3f) ? "FAIL? near 0 — divider/ADC issue or no VBAT" :
                             "check divider ratio");
}

static void testLatch() {
  // v0.13: GPIO19 is PWR_HOLD (OUTPUT). DO NOT pinMode(INPUT) — that tri-states
  // it, R_PD pulls /LATCH_Q low, and the board powers ITSELF off the moment it's
  // off-pad. digitalRead() on an OUTPUT returns the latched output register.
  int q = digitalRead(PIN_PWR_HOLD);
  Serial.printf("[LATCH] PWR_HOLD (GPIO19) driven = %d  -> boost latch %s (held by firmware)\n",
                q, q ? "ON / will survive lift-off pad" : "OFF (?) — board would die on lift");
}

// ---------------- LEDs ----------------
static void ledInit() {
  pinMode(LED_RED, OUTPUT);   digitalWrite(LED_RED, HIGH);    // active LOW -> HIGH = off
  pinMode(LED_WHITE, OUTPUT); digitalWrite(LED_WHITE, HIGH);
  pinMode(LED_CYAN, OUTPUT);  digitalWrite(LED_CYAN, HIGH);
}
static void ledTest() {
  Serial.println(F("[LED] cycling D4 red(33) / D5 white(32) / D6 cyan(26) — watch the bottom edge"));
  const int pins[3] = {LED_RED, LED_WHITE, LED_CYAN};
  const char* names[3] = {"D4 red", "D5 white", "D6 cyan"};
  for (int i = 0; i < 3; i++) {
    Serial.printf("       %s ON\n", names[i]);
    digitalWrite(pins[i], LOW);  delay(500);
    digitalWrite(pins[i], HIGH); delay(150);
  }
  Serial.println(F("[LED] done (all off)"));
}

// ---------------- I2C ----------------
static void i2cScan() {
  Serial.println(F("[I2C] scanning SDA=21 SCL=22 ..."));
  int found = 0;
  for (uint8_t a = 1; a < 127; a++) {
    Wire.beginTransmission(a);
    if (Wire.endTransmission() == 0) {
      Serial.printf("      device @ 0x%02X%s\n", a,
        a == BNO_ADDR ? "  <- BNO085 (expected)" :
        a == BNO_ALT  ? "  <- BNO085 (Adafruit addr 0x4A)" :
        a == DPS_ADDR ? "  <- DPS310" : "");
      found++;
    }
  }
  Serial.printf("[I2C] %d device(s). BNO085 %s\n", found,
                found ? "see above" : "NONE — check J8 populated + pinout (risk: mis-wired J8 shorts SCL->GND)");
}

// ---------------- microSD (NON-BLOCKING) ----------------
static bool testSD() {
  Serial.printf("[SD] HSPI CLK=%d MOSI=%d MISO=%d CS=%d\n", SD_CLK, SD_MOSI, SD_MISO, SD_CS);
  pinMode(SD_CS, OUTPUT); digitalWrite(SD_CS, HIGH);
  SD.end();
  sdSPI.end();
  sdSPI.begin(SD_CLK, SD_MISO, SD_MOSI, SD_CS);
  const uint32_t speeds[3] = {4000000, 1000000, 400000};
  g_sdOK = false;
  for (int i = 0; i < 3 && !g_sdOK; i++) {
    Serial.printf("[SD] trying %lu Hz... ", (unsigned long)speeds[i]);
    g_sdOK = SD.begin(SD_CS, sdSPI, speeds[i]);
    Serial.println(g_sdOK ? "OK" : "fail");
  }
  if (!g_sdOK) {
    Serial.println(F("[SD] === FAILED (continuing — NOT halting) ==="));
    Serial.println(F("     B1 pins MATCH firmware, so suspect HARDWARE: reflow J5 slot,"));
    Serial.println(F("     check V3V3 at SD VCC, the 10K pull-ups on CLK/MOSI/MISO/CS, reseat card."));
    return false;
  }
  uint8_t ct = SD.cardType();
  const char* cts = ct == CARD_MMC ? "MMC" : ct == CARD_SD ? "SDSC" : ct == CARD_SDHC ? "SDHC" : "UNKNOWN";
  Serial.printf("[SD] OK — type=%s size=%lluMB\n", cts, SD.cardSize() / (1024ULL * 1024ULL));
  // root listing
  File root = SD.open("/");
  if (root) {
    Serial.println(F("[SD] root:"));
    for (File f = root.openNextFile(); f; f = root.openNextFile())
      Serial.printf("       %s%s  %u\n", f.name(), f.isDirectory() ? "/" : "", (unsigned)f.size());
    root.close();
  }
  // write/read/delete round-trip
  const char* tp = "/b1_bringup_test.txt";
  File w = SD.open(tp, FILE_WRITE);
  if (w) {
    w.println("B1 bringup r/w ok"); w.close();
    File r = SD.open(tp);
    if (r) { Serial.printf("[SD] r/w test: read back \"%s\"\n", r.readStringUntil('\n').c_str()); r.close(); }
    SD.remove(tp);
    Serial.println(F("[SD] write/read/delete round-trip PASS"));
  } else {
    Serial.println(F("[SD] mounted but write FAILED (card write-protect / FS issue)"));
  }
  return true;
}

// ---------------- GNSS UART ----------------
static void testGNSS(uint32_t ms) {
  const uint32_t bauds[2] = {115200, 9600};
  for (int b = 0; b < 2; b++) {
    Serial2.end();
    Serial2.begin(bauds[b], SERIAL_8N1, GNSS_RX, GNSS_TX);
    Serial.printf("[GNSS] listening UART2 RX=16 @ %lu for %lums...\n", (unsigned long)bauds[b], (unsigned long)ms);
    uint32_t t0 = millis(); int bytes = 0; bool nmea = false; String s;
    while (millis() - t0 < ms) {
      while (Serial2.available()) {
        char c = Serial2.read(); bytes++;
        if (c == '$') nmea = true;
        if (nmea && s.length() < 90) { if (c == '\n') { Serial.printf("       %s\n", s.c_str()); s = ""; } else if (c != '\r') s += c; }
      }
    }
    Serial.printf("[GNSS] @%lu: %d bytes, NMEA %s\n", (unsigned long)bauds[b], bytes, nmea ? "SEEN -> alive" : "none");
    if (bytes) return;   // got data at this baud; stop
  }
  Serial.println(F("[GNSS] no bytes at either baud — check LC29HEA power(V3V3), TXD1->GPIO16 wiring, D_SEL pulls"));
}

// ---------------- TFT ----------------
#if TEST_TFT
static void testTFT() {
  pinMode(TFT_BL, OUTPUT); digitalWrite(TFT_BL, HIGH);   // backlight full on
  tft.init();
  tft.setRotation(0);
  tft.fillScreen(TFT_BLACK);
  tft.setTextColor(TFT_WHITE, TFT_BLACK);
  tft.setTextDatum(TL_DATUM);
  tft.drawString("B1 BRING-UP", 8, 8, 4);
  tft.drawString("TFT OK", 8, 44, 4);
  // RGB bars to verify color order
  int w = tft.width();
  tft.fillRect(0, 90, w, 30, TFT_RED);
  tft.fillRect(0, 122, w, 30, TFT_GREEN);
  tft.fillRect(0, 154, w, 30, TFT_BLUE);
  tft.setTextColor(TFT_WHITE, TFT_BLACK);
  char buf[40];
  snprintf(buf, sizeof(buf), "BAT %.2fV", readBattV());
  tft.drawString(buf, 8, 200, 4);
  snprintf(buf, sizeof(buf), "SD %s  BNO %s", g_sdOK ? "OK" : "FAIL",
           (Wire.beginTransmission(BNO_ADDR), Wire.endTransmission() == 0) ? "OK" : "--");
  tft.drawString(buf, 8, 236, 4);
  Serial.println(F("[TFT] drew test pattern (R/G/B bars + status). If blank: backlight=GPIO25, check J9 seating + User_Setup.h"));
}
#else
static void testTFT() { Serial.println(F("[TFT] disabled (TEST_TFT 0)")); }
#endif

// ---------------- orchestration ----------------
static void runAll() {
  banner();
  testBattery();
  testLatch();
  i2cScan();
  testSD();           // never halts
  testGNSS(2000);
  testTFT();
  ledTest();
  line();
  Serial.println(F("[DONE] self-test complete. Menu: a sd i b g l q t m h"));
  line();
}

static void help() {
  Serial.println(F("Commands: a=all  sd=retry SD  i=I2C  b=battery  g=GNSS  l=LEDs  q=latch  t=TFT  m=monitor  h=help"));
}

void setup() {
  // v0.13 Qi-power: latch our own power ON before anything slow. On the pad we
  // boot via the D7/Qi rail; this drives /LATCH_Q (R28 0R) so the MT3608 boost
  // stays enabled and V5_SW survives being lifted off the pad. WITHOUT this the
  // board dies the instant Qi power is removed (see B1_V013_QI_POWER.md §6).
  pinMode(PIN_PWR_HOLD, OUTPUT);
  digitalWrite(PIN_PWR_HOLD, HIGH);

  Serial.begin(115200);
  delay(400);
  analogReadResolution(12);
  analogSetPinAttenuation(PIN_VBAT, ADC_11db);
  ledInit();
  Wire.begin(PIN_SDA, PIN_SCL);
  Wire.setClock(100000);
  runAll();
  help();
}

void loop() {
  if (!Serial.available()) return;
  String cmd = Serial.readStringUntil('\n');
  cmd.trim();
  if (cmd == "a")       runAll();
  else if (cmd == "sd") testSD();
  else if (cmd == "i")  i2cScan();
  else if (cmd == "b")  testBattery();
  else if (cmd == "g")  testGNSS(3000);
  else if (cmd == "l")  ledTest();
  else if (cmd == "q")  testLatch();
  else if (cmd == "t")  testTFT();
  else if (cmd == "h" || cmd == "?") help();
  else if (cmd == "m") {
    Serial.println(F("[MON] battery + latch every 1s; send any line to stop"));
    while (!Serial.available()) {
      Serial.printf("  BAT %.2fV  PWR_HOLD %d  heap %u\n", readBattV(), digitalRead(PIN_PWR_HOLD), ESP.getFreeHeap());
      delay(1000);
    }
    Serial.readStringUntil('\n');
  }
  else if (cmd.length()) Serial.printf("? '%s' — h for help\n", cmd.c_str());
}
