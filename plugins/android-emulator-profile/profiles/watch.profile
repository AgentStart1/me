# Required
AVD_NAME=watch-android-36_1-android-wear
SYS_IMG_PKG='system-images;android-36.1;android-wear'

# avdmanager create avd mappings
AVDMANAGER_VALUE_device=wearos_small_round
AVDMANAGER_VALUE_path=

# AVD config.ini overrides. Use double underscores for dots in config keys;
# single underscores are preserved. For example:
# EMULATOR_CONFIG_hw__gpu__enabled=yes
# EMULATOR_CONFIG_hw__ramSize=4G
EMULATOR_CONFIG_disk__dataPartition__size=50G

# Display
EMULATOR_DISPLAY=:0

# Common startup flags
# Check https://developer.android.google.cn/studio/run/emulator-commandline
# for the supported emulator command-line arguments.
EMULATOR_FLAG_accel_off=false
EMULATOR_FLAG_delay_adb=false
EMULATOR_FLAG_no_audio=true
EMULATOR_FLAG_no_boot_anim=true
EMULATOR_FLAG_nojni=false
EMULATOR_FLAG_no_snapshot=true
EMULATOR_FLAG_no_snapshot_load=false
EMULATOR_FLAG_no_snapshot_save=false
EMULATOR_FLAG_no_window=false
EMULATOR_FLAG_netfast=false
EMULATOR_FLAG_read_only=false
EMULATOR_FLAG_show_kernel=false
EMULATOR_FLAG_verbose=false
EMULATOR_FLAG_wipe_data=false

# Value-style arguments
EMULATOR_VALUE_accel=
EMULATOR_VALUE_camera_back=
EMULATOR_VALUE_camera_front=
EMULATOR_VALUE_cores=
EMULATOR_VALUE_data=
EMULATOR_VALUE_dns_server=
EMULATOR_VALUE_gpu=
EMULATOR_VALUE_grpc=
EMULATOR_VALUE_http_proxy=
EMULATOR_VALUE_memory=
EMULATOR_VALUE_netdelay=
EMULATOR_VALUE_netspeed=
EMULATOR_VALUE_port=
EMULATOR_VALUE_ports=
EMULATOR_VALUE_prop=
EMULATOR_VALUE_report_console=
EMULATOR_VALUE_shell_serial=
EMULATOR_VALUE_skin=
EMULATOR_VALUE_timezone=
