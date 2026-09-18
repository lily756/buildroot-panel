#!/bin/bash
set -e

STARTDIR=$(pwd)
SELFDIR=$(dirname "$(realpath "${0}")")
MKIMAGE="${HOST_DIR}/bin/mkimage"
IMAGE_ITS="kernel.its"
OUTPUT_NAME="kernel.itb"

[ $# -eq 2 ] || {
	echo "SYNTAX: $0 <output dir> <u-boot-with-spl image>"
	echo "Given: $*"
	exit 1
}

cp board/allwinner/generic/kernel.its "${BINARIES_DIR}"
cd "${BINARIES_DIR}"
"${MKIMAGE}" -f "${IMAGE_ITS}" "${OUTPUT_NAME}"
rm "${IMAGE_ITS}"

cd "${STARTDIR}"
"${HOST_DIR}/bin/python3" "${SELFDIR}/bmp-to-uboot.py" \
	"${STARTDIR}/board/allwinner/generic/splash.bmp" \
	"${BINARIES_DIR}/splash.bmp"

# This board boots from its soldered 16 MiB SPI-NOR. Avoid producing the
# unrelated 35 MiB SD-card and 129 MiB raw-NAND images on every build.
support/scripts/genimage.sh "${1}" -c board/widora/mangopi/r3-aic8800d40/genimage-nor.cfg
