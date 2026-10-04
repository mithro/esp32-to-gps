/* user_config_override.h - ESP32-C3 + GPS receiver (github.com/mithro/esp32-to-gps)
 * SPDX-License-Identifier: GPL-3.0-or-later
 * Copied into tasmota/ of the mithro/Tasmota checkout by firmware/build.py.
 * Only #define / #undef here; the driver is xsns_60_GPS.ino in the fork. */
#ifndef _USER_CONFIG_OVERRIDE_H_
#define _USER_CONFIG_OVERRIDE_H_

#ifndef USE_GPS
#define USE_GPS                         // the GPS driver, xsns_60_GPS.ino
#endif
#ifndef USE_GPS_VELOCITY
#define USE_GPS_VELOCITY                // speed and course in the GPS sensor JSON and web page
#endif
#ifndef USE_UFILESYS
#define USE_UFILESYS                    // /gnss.cfg: the Gps* command settings
#endif

#undef  PROJECT
#define PROJECT             "gps"
#undef  FRIENDLY_NAME
#define FRIENDLY_NAME       "GPS"
#undef  OTA_URL
#define OTA_URL             ""          // a stock tasmota32c3 OTA image would not have this driver
#undef  APP_TIMEZONE
#define APP_TIMEZONE        99          // use the TimeZone / TimeDst / TimeStd settings

/* ---------- boot-safety guardrails, as in esp32-to-433mhz ----------
 * Configuration changes that would remove the USB / ROM-download recovery
 * path become build errors here, rather than a node that cannot be recovered. */

// The USB-Serial-JTAG console must stay the console (board esp32c3, never the UART-only esp32c3ser).
#if defined(ESP32C3) && !defined(USE_USB_CDC_CONSOLE)
#error "esp32-to-gps: the USB-Serial-JTAG console must stay enabled (board esp32c3, never esp32c3ser)."
#endif
#if defined(CONFIG_ESP_CONSOLE_NONE)
#error "esp32-to-gps: CONFIG_ESP_CONSOLE_NONE disables the console."
#endif

// Secure boot, flash encryption and disabling ROM download burn eFuses and can block esptool recovery for good.
#if defined(CONFIG_SECURE_BOOT) || defined(CONFIG_SECURE_FLASH_ENC_ENABLED) || defined(CONFIG_FLASH_ENCRYPTION_ENABLED)
#error "esp32-to-gps: secure boot / flash encryption must not be enabled."
#endif
#if defined(CONFIG_SECURE_DISABLE_ROM_DL_MODE) || defined(CONFIG_SECURE_UART_ROM_DL_MODE)
#error "esp32-to-gps: ROM download mode must stay reachable."
#endif

// A crash must reboot, not hang.
#if defined(CONFIG_ESP_TASK_WDT_EN) && !defined(CONFIG_ESP_TASK_WDT_INIT)
#error "esp32-to-gps: the task watchdog must be initialised."
#endif

#endif  // _USER_CONFIG_OVERRIDE_H_
