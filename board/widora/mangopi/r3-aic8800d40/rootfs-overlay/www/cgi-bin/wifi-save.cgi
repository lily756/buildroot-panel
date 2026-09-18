#!/bin/sh

PATH=${WIFI_PROVISION_PATH:-/sbin:/usr/sbin:/bin:/usr/bin}
LC_ALL=C
export PATH LC_ALL
set -f

WIFI_DIR=${WIFI_PROVISION_CONFIG_DIR:-/etc/wifi}
WPA_CONFIG=${WIFI_DIR}/wpa_supplicant.conf
RESTART_SCRIPT=${WIFI_PROVISION_RESTART_SCRIPT:-/etc/init.d/S55wifi-provision}
SAVE_LOCK=${WIFI_PROVISION_SAVE_LOCK:-/run/wifi-provision-save.lock}
MAX_REQUEST_SIZE=1024
TEMP_FILE=

cleanup()
{
	[ -n "$TEMP_FILE" ] && rm -f "$TEMP_FILE"
}
trap cleanup 0 1 2 15

emit_page()
{
	status=$1
	title=$2
	message=$3
	printf 'Status: %s\r\n' "$status"
	printf 'Content-Type: text/html; charset=UTF-8\r\n'
	printf 'Cache-Control: no-store\r\n'
	printf 'X-Content-Type-Options: nosniff\r\n'
	printf 'X-Frame-Options: DENY\r\n'
	printf "Content-Security-Policy: default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'\r\n"
	printf 'Referrer-Policy: no-referrer\r\n'
	printf '\r\n'
	printf '%s\n' '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
	printf '%s\n' '<style>body{font-family:sans-serif;max-width:32rem;margin:10vh auto;padding:1.5rem;line-height:1.6;color:#18202a}a{color:#1264d8}</style></head><body>'
	printf '<h1>%s</h1><p>%s</p>' "$title" "$message"
	printf '%s\n' '<p><a href="/">返回配网页面</a></p></body></html>'
}

fail_request()
{
	emit_page "$1" "配置未保存" "$2"
	exit 1
}

valid_percent_encoding()
{
	without_escapes=$(printf '%s' "$1" |
		sed 's/%[0-9A-Fa-f][0-9A-Fa-f]//g')
	case "$without_escapes" in
		*%*) return 1 ;;
	esac
	return 0
}

contains_encoded_control()
{
	normalized=$(printf '%s' "$1" | tr 'A-F' 'a-f')
	case "$normalized" in
		*%0[0-9a-f]*|*%1[0-9a-f]*|*%7f*) return 0 ;;
	esac
	return 1
}

contains_control_byte()
{
	printf '%s' "$1" | od -An -tu1 |
		awk '{ for (i = 1; i <= NF; i++) if ($i < 32 || $i == 127) bad = 1 }
		     END { exit bad ? 0 : 1 }'
}

case "$REMOTE_ADDR" in
	192.168.4.*) ;;
	*) fail_request '403 Forbidden' '只允许从设备配置热点提交请求。' ;;
esac

[ "$REQUEST_METHOD" = POST ] ||
	fail_request '405 Method Not Allowed' '只接受 POST 请求。'

case "${CONTENT_TYPE%%;*}" in
	application/x-www-form-urlencoded) ;;
	*) fail_request '415 Unsupported Media Type' '请求格式必须为表单编码。' ;;
esac

case "$CONTENT_LENGTH" in
	''|*[!0-9]*) fail_request '400 Bad Request' '请求长度无效。' ;;
esac
[ "$CONTENT_LENGTH" -gt 0 ] 2>/dev/null ||
	fail_request '400 Bad Request' '请求内容为空。'
[ "$CONTENT_LENGTH" -le "$MAX_REQUEST_SIZE" ] 2>/dev/null ||
	fail_request '413 Payload Too Large' '请求内容过长。'

FORM_DATA=$(dd bs=1 count="$CONTENT_LENGTH" 2>/dev/null) ||
	fail_request '400 Bad Request' '无法读取请求内容。'
ACTUAL_LENGTH=$(printf '%s' "$FORM_DATA" | wc -c | tr -d '[:space:]')
[ "$ACTUAL_LENGTH" = "$CONTENT_LENGTH" ] ||
	fail_request '400 Bad Request' '请求内容不完整。'

old_ifs=$IFS
IFS='&'
set -- $FORM_DATA
IFS=$old_ifs
[ "$#" -eq 2 ] ||
	fail_request '400 Bad Request' '表单字段不完整。'

SSID_RAW=
PSK_RAW=
seen_ssid=0
seen_psk=0
for field do
	case "$field" in
		ssid=*)
			[ "$seen_ssid" -eq 0 ] ||
				fail_request '400 Bad Request' 'SSID 字段重复。'
			SSID_RAW=${field#ssid=}
			seen_ssid=1
			;;
		psk=*)
			[ "$seen_psk" -eq 0 ] ||
				fail_request '400 Bad Request' '密码字段重复。'
			PSK_RAW=${field#psk=}
			seen_psk=1
			;;
		*) fail_request '400 Bad Request' '表单包含未知字段。' ;;
	esac
done
[ "$seen_ssid" -eq 1 ] && [ "$seen_psk" -eq 1 ] ||
	fail_request '400 Bad Request' '表单字段不完整。'

valid_percent_encoding "$SSID_RAW" && valid_percent_encoding "$PSK_RAW" ||
	fail_request '400 Bad Request' '表单包含无效的转义序列。'
contains_control_byte "$SSID_RAW" &&
	fail_request '400 Bad Request' 'SSID 包含控制字符。'
contains_control_byte "$PSK_RAW" &&
	fail_request '400 Bad Request' '密码包含控制字符。'
contains_encoded_control "$SSID_RAW" &&
	fail_request '400 Bad Request' 'SSID 包含控制字符。'
contains_encoded_control "$PSK_RAW" &&
	fail_request '400 Bad Request' '密码包含控制字符。'

SSID=$(httpd -d "$SSID_RAW") ||
	fail_request '400 Bad Request' 'SSID 解码失败。'
PSK=$(httpd -d "$PSK_RAW") ||
	fail_request '400 Bad Request' '密码解码失败。'

SSID_LENGTH=$(printf '%s' "$SSID" | wc -c | tr -d '[:space:]')
[ "$SSID_LENGTH" -ge 1 ] && [ "$SSID_LENGTH" -le 32 ] ||
	fail_request '400 Bad Request' 'SSID 必须为 1–32 字节。'
contains_control_byte "$SSID" &&
	fail_request '400 Bad Request' 'SSID 包含控制字符。'

PSK_LENGTH=$(printf '%s' "$PSK" | wc -c | tr -d '[:space:]')
[ "$PSK_LENGTH" -ge 8 ] && [ "$PSK_LENGTH" -le 63 ] ||
	fail_request '400 Bad Request' '密码必须为 8–63 个字符。'
case "$PSK" in
	*[![:print:]]*) fail_request '400 Bad Request' '密码只能包含可打印 ASCII 字符。' ;;
esac

command -v wpa_passphrase >/dev/null 2>&1 ||
	fail_request '500 Internal Server Error' '系统缺少密码处理工具。'

SSID_HEX=$(printf '%s' "$SSID" | od -An -tx1 | tr -d '[:space:]')
PSK_HEX=$(printf '%s\n' "$PSK" | wpa_passphrase "$SSID" |
	sed -n 's/^[[:space:]]*psk=\([0-9A-Fa-f]\{64\}\)$/\1/p' |
	head -n 1)
[ "${#PSK_HEX}" -eq 64 ] ||
	fail_request '500 Internal Server Error' '无法生成安全的网络凭据。'

mkdir -p "$WIFI_DIR" ||
	fail_request '500 Internal Server Error' '无法创建配置目录。'
exec 9>"$SAVE_LOCK" ||
	fail_request '500 Internal Server Error' '无法创建配置锁。'
flock -n 9 ||
	fail_request '409 Conflict' '另一项配置正在保存，请稍后重试。'

umask 077
TEMP_FILE=$(mktemp "${WPA_CONFIG}.tmp.XXXXXX") ||
	fail_request '500 Internal Server Error' '无法创建临时配置。'
{
	printf '%s\n' 'ctrl_interface=/run/wpa_supplicant'
	printf '%s\n' 'update_config=0'
	printf '%s\n' 'country=CN'
	printf '%s\n' 'network={'
	printf '\tssid=%s\n' "$SSID_HEX"
	printf '\tpsk=%s\n' "$PSK_HEX"
	printf '%s\n' '    key_mgmt=WPA-PSK'
	printf '%s\n' '    scan_ssid=1'
	printf '%s\n' '}'
} > "$TEMP_FILE" ||
	fail_request '500 Internal Server Error' '无法写入临时配置。'
chmod 0600 "$TEMP_FILE" ||
	fail_request '500 Internal Server Error' '无法保护配置文件。'
mv -f "$TEMP_FILE" "$WPA_CONFIG" ||
	fail_request '500 Internal Server Error' '无法保存配置。'
TEMP_FILE=
sync

# Do not retain the clear-text passphrase longer than needed.
PSK=
PSK_RAW=

emit_page '200 OK' '配置已保存' '设备将在几秒后关闭配置热点并连接目标 Wi-Fi。'
(
	sleep 2
	"$RESTART_SCRIPT" restart
) </dev/null >/dev/null 2>&1 &

exit 0
