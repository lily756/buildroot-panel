# Widora MangoPi R3 AIC8800D40

This is a MangoPi R3 derivative with an AIC8800D40 Wi-Fi module on the
F1C200s USB OTG data pair and a ZJY400-8532ANT RGB panel.

## Pin ownership

- USB-DP/USB-DM: shared by U-Boot's DFU gadget and the Linux AIC8800D40 host.
- PE4: `WIFI_EN`, low in U-Boot and driven high by `S45aic8800` immediately
  before the Linux AIC USB modules are loaded.
- PD0..PD21: RGB666 LCD data, PCLK, DE, HSYNC, and VSYNC.
- PE11: active-low LCD reset, controlled once at boot by `S00lcd-reset`.
- PE12: PWM0 output to the board's backlight boost/current driver.
- PE0/PE1: I2C2 SCL/SDA. I2C0 is disabled because its PD0/PD12 pin group
  conflicts with RGB666.
- PE7..PE10: module UART and flow-control traces; disabled because this
  configuration enables Wi-Fi over USB only.
- UART1: serial console (`ttyS0`, 115200 baud); the DT `serial0` alias keeps
  the Linux line number aligned with U-Boot.

The R3 camera, GT911/tsc2007 touch, codec, VE/ION, SPI1, and UART2 board
overrides are intentionally omitted.  Their SoC controller definitions remain
disabled by default in `suniv-f1c100s.dtsi` and claim no pins on this board.

## Display

The module datasheet specifies 720x720 active pixels, RGB666, 3.3 V VCI,
active-high DE, rising-edge sampling, and an active-low RESET_N assertion of at
least 10 us. The early userspace `S00lcd-reset` service holds PE11 low for 20 ms
and then leaves it high. Its 4S2P backlight requires approximately 12.8 V at
40 mA; PE12 must
therefore control the external constant-current boost circuit and must never
drive the LED strings directly.

The module vendor supplied the following porch and sync-width values.  The
pixel clock remains at the conservative 30 MHz board setting:

| Item | Value |
| --- | ---: |
| Active area | 720 x 720 |
| Pixel clock | 30 MHz |
| H front/back/sync | 106 / 120 / 60 pixels |
| V front/back/sync | 20 / 20 / 4 lines |
| HSYNC / VSYNC | active low |
| DE | active high |
| Pixel data | driven on falling edge, sampled on rising edge |
| Nominal refresh | about 39.03 Hz |

The Linux panel descriptor, U-Boot mode, and RGB666 pinmux must be changed
together if measurements require different timings.

U-Boot loads `splash.bmp` from MMC or from the dedicated 512 KiB NOR/NAND
partition and displays it centered. The image is supplied by
`board/allwinner/generic/splash.bmp`. The post-image script converts a 32-bit
bitfield BMP to the uncompressed 24-bit `BI_RGB` encoding accepted by this
U-Boot. A replacement must fit in 512 KiB after conversion; a full-screen
720x720 image should use an 8-bit palette to fit. Linux enables fbdev, fbcon,
deferred framebuffer takeover, and the standard boot logo.

Framebuffer test programs installed in `/usr/bin` are:

    fb-test
    fb-test-rect
    fb-test-offset
    fb-test-perf

## Wi-Fi and AP provisioning

The image includes the AIC driver/firmware, wireless-regdb, `iw`,
`wpa_supplicant`, `wpa_cli`, `wpa_passphrase`, `hostapd`, `dnsmasq`,
BusyBox `ip`, and `iptables`. Kernel conntrack, IPv4 filtering, and NAT support
are enabled for an optional routed AP configuration.

`S45aic8800` registers both `aic_load_fw` and `aic8800_fdrv` while PE4 still
holds the module off. It then enables the module and waits for the USB identity
to change from the boot-ROM PID (`8d80`/`8d40`) to the runtime PID
(`8d81`/`8d41`) and for `wlan0`. Registering the runtime driver in advance is
important because this module can expose the runtime USB function for only a
short window. `S55wifi-provision` subsequently behaves as follows:

1. If `/etc/wifi/wpa_supplicant.conf` contains credentials, try STA association
   and DHCP.
2. If credentials are absent or STA setup fails, start a WPA2 provisioning AP,
   DHCP/DNS service, and a local HTTP portal.
3. The portal validates the submitted SSID/passphrase, stores only a hex SSID
   and derived PSK using an atomic update, then restarts the Wi-Fi state machine.

Bring-up AP details:

    SSID: MangoPi-Setup
    Passphrase: mangopi8800
    Portal: http://192.168.4.1/

The shared passphrase is only suitable for development. Production images must
generate a unique SSID and AP passphrase for every device. To discard saved STA
credentials and return to provisioning mode:

    rm -f /etc/wifi/wpa_supplicant.conf
    /etc/init.d/S55wifi-provision restart

The current mode is available in `/run/wifi-provision.mode` (`sta` or `ap`).

The vendor driver normally reserves 1000 20-KiB RX buffers (about 20 MiB) at
module load time.  This is disabled for the board's 32 MiB DRAM; receive
buffers are allocated on demand. The fullmac driver is also built with its
supported `CONFIG_ONE_TXQ` mode. Without it, the vendor default exposes 257
Linux transmit queues and bringing `wlan0` up tries to allocate a qdisc for
each queue, exhausting non-CMA memory. The driver's internal per-station/TID
scheduling remains enabled. BusyBox mdev replaces eudev, and `haveged` is not
installed: eudev's hardware database consumed about 15 MiB of uncompressed
rootfs space, while haveged's roughly 2.7-MiB resident set caused
`module_alloc()` to invoke the OOM killer while loading `aic8800_fdrv`.

The kernel profile also removes the unused ALSA, V4L2/CSI, Cedar VE/ION,
mac80211, USB gadget, EHCI/OHCI, HID, USB-storage, ext4, SPI-NAND, swap,
cgroup, namespace, perf, AIO, and io_uring paths. CMA is 6 MiB: enough for two
720x720 XRGB8888 buffers with alignment, while making 2 MiB more normal memory
available to the Wi-Fi driver.

## DFU and storage layout

U-Boot holds PE4 low so the internal USB device cannot contend with an external
DFU host. It removes the MUSB gadget before Linux handoff; Linux then switches
the controller to host mode. `S45aic8800` exports GPIO 132 (PE4), keeps it low
while registering both AIC modules, then sets it high. A device-tree GPIO hog
is deliberately not used:
Linux 5.4's sunxi PIO driver processes the hog before its GPIO pin ranges are
registered, causing `gpiochip_add_data_with_key()` to fail with
`-EPROBE_DEFER`. This depends on PE4 actually isolating/resetting the module on
the assembled board and must be verified electrically.

There is a one-second autoboot interruption window. A valid MMC or SPI image is
booted before entering DFU; if normal boot returns with an error, U-Boot first
offers a five-second DFU recovery window and then waits indefinitely. From the
U-Boot prompt, start a backend explicitly with one of:

    setenv dfu_mmc_dev 0; run dfu_mmc
    run dfu_nor
    run dfu_nand

On the build host, `output/host/bin/dfu-util -l` lists the exact alternate
names. MMC exposes `kernel.itb` and `splash.bmp`; NOR/NAND expose `kernel` and
`splash`. The flash layouts use the same logical MTD indices:

| Index | Partition |
| ---: | --- |
| 0 | u-boot |
| 1 | splash |
| 2 | kernel |
| 3 | rom |
| 4 | overlay |
| 5 | vendor (NAND only) |

The NAND device-tree children intentionally list `overlay` before `vendor` so
the boot arguments remain identical for NOR and NAND even though their physical
offsets are in the opposite order.

## Build

    make widora_mangopi_r3_aic8800d40_defconfig
    make

The AIC driver recognizes the D40 USB ID and uses the bundled `aic8800D80`
firmware compatibility directory. The post-image step produces only the 16 MiB
NOR image; check that `rootfs.squashfs` still fits its 8.5 MiB `rom` partition
after adding application packages.
