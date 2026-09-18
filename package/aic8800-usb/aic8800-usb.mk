################################################################################
#
# aic8800-usb
#
################################################################################

AIC8800_USB_VERSION = 5.0_2025_1231_b3b80d09
AIC8800_USB_SITE = $(AIC8800_USB_PKGDIR)/src
AIC8800_USB_SITE_METHOD = local
AIC8800_USB_LICENSE = GPL-2.0, proprietary firmware blobs
AIC8800_USB_MODULE_SUBDIRS = drivers/aic8800
AIC8800_USB_MODULE_MAKE_OPTS = \
	CONFIG_PLATFORM_UBUNTU=y \
	CONFIG_RWNX_DBG=n

# The vendor default reserves 1000 RX buffers of 20 KiB each while loading
# aic_load_fw.  That roughly 20 MiB pool cannot fit on a 32 MiB suniv system;
# The local vendor source forces the normal on-demand RX path in its top-level
# Makefile; command-line defaults are overridden there by the vendor build.

define AIC8800_USB_INSTALL_FIRMWARE
	$(INSTALL) -d $(TARGET_DIR)/lib/firmware/aic8800D80
	$(INSTALL) -m 0644 $(@D)/firmware/aic8800D80/* \
		$(TARGET_DIR)/lib/firmware/aic8800D80/
endef

AIC8800_USB_POST_INSTALL_TARGET_HOOKS += AIC8800_USB_INSTALL_FIRMWARE

$(eval $(kernel-module))
$(eval $(generic-package))
