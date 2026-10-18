# ILIFE A30 Pro (product 5309qt4sjd4uz4qz) — datapoints

From the Tuya thing model (`/v2.0/cloud/thing/{id}/model`) and shadow values, 2026-10-18.
The dp id is what the robot uses on the LAN (Tuya protocol 3.3).

Values that describe the owner's home life (schedules, do-not-disturb window, saved
maps and per-room settings, lifetime totals) are left out as `<redacted>`: they tell
when a home is empty. Their formats are in `a30pro-zone-formats.md` and `tuya_rooms.py`.

| dp | code | access | type | spec | value at capture |
|---|---|---|---|---|---|
| 1 | switch_go | rw | bool | {} | False |
| 2 | pause | rw | bool | {} | False |
| 3 | switch_charge | rw | bool | {} | False |
| 4 | mode | rw | enum | {"range": ["smart", "chargego", "zone", "pose", "part", "edge", "explore", "exploreclean"] | smart |
| 5 | status | ro | enum | {"range": ["standby", "smart", "zone_clean", "part_clean", "cleaning", "paused", "goto_pos | base_charging |
| 6 | clean_time | ro | value | {"max": 9999, "min": 0, "scale": 0, "step": 1, "unit": "min"} | 0 |
| 7 | clean_area | ro | value | {"max": 9999, "min": 0, "scale": 0, "step": 1, "unit": "\u33a1"} | 0 |
| 8 | residual_electricity | ro | value | {"max": 100, "min": 0, "scale": 0, "step": 1, "unit": "%"} | 27 |
| 9 | suction | rw | enum | {"range": ["strong", "normal", "gentle", "max", "closed"]} | strong |
| 10 | cistern | rw | enum | {"range": ["low", "middle", "high", "closed"]} | high |
| 11 | seek | rw | bool | {} | False |
| 12 | direction_control | rw | enum | {"range": ["foward", "backward", "turn_left", "turn_right", "stop"]} | foward |
| 13 | reset_map | rw | bool | {} | False |
| 14 | path_data | rw | raw | {"maxlen": 128} | None |
| 15 | command_trans | rw | raw | {"maxlen": 128} | qgAEGwACAB0= |
| 16 | request | rw | enum | {"range": ["get_map", "get_path", "get_both"]} | get_map |
| 17 | edge_brush | ro | value | {"max": 900, "min": 0, "scale": 0, "step": 1, "unit": "min"} | 630 |
| 18 | reset_edge_brush | rw | bool | {} | False |
| 19 | roll_brush | ro | value | {"max": 1800, "min": 0, "scale": 0, "step": 1, "unit": "min"} | 1440 |
| 20 | reset_roll_brush | rw | bool | {} | False |
| 21 | filter | ro | value | {"max": 900, "min": 0, "scale": 0, "step": 1, "unit": "min"} | 540 |
| 22 | reset_filter | rw | bool | {} | False |
| 25 | switch_disturb | rw | bool | {} | False |
| 26 | volume_set | rw | value | {"max": 10, "min": 0, "scale": 0, "step": 1, "unit": "%"} | 1 |
| 27 | break_clean | rw | bool | {} | True |
| 28 | fault | ro | bitmap | {"label": ["bumper_fault", "obs_fault", "wall_fault", "cliff_fault", "land_fault", "nosewh | 0 |
| 29 | clean_area_total | ro | value | {"max": 2073741824, "min": 0, "scale": 0, "step": 1, "unit": "\u33a1"} | <redacted> |
| 30 | clean_count_total | ro | value | {"max": 2073741824, "min": 0, "scale": 0, "step": 1, "unit": ""} | <redacted> |
| 31 | clean_time_total | ro | value | {"max": 2073741824, "min": 0, "scale": 0, "step": 1, "unit": "min"} | <redacted> |
| 35 | voice_data | rw | raw | {"maxlen": 128} | qgAHNQAAAAAAADU= |
| 37 | dust_collection_num | rw | value | {"max": 99999, "min": 0, "scale": 0, "step": 1, "unit": ""} | 1 |
| 38 | dust_collection_switch | rw | bool | {} | False |
| 45 | auto_boost | rw | bool | {} | True |
| 120 | Schedule1 | rw | string | {"maxlen": 255} | <redacted> |
| 121 | Schedule2 | rw | string | {"maxlen": 255} | <redacted> |
| 122 | Schedule3 | rw | string | {"maxlen": 255} | <redacted> |
| 123 | Schedule4 | rw | string | {"maxlen": 255} | <redacted> |
| 124 | Schedule5 | rw | string | {"maxlen": 255} | <redacted> |
| 125 | Schedule6 | rw | string | {"maxlen": 255} | <redacted> |
| 126 | Schedule7 | rw | string | {"maxlen": 255} | <redacted> |
| 127 | InitStatus | ro | value | {"max": 255, "min": 0, "scale": 0, "step": 1, "unit": ""} | 1 |
| 128 | SaveMap | rw | string | {"maxlen": 255} | <redacted> |
| 129 | CleanPartitionData | rw | string | {"maxlen": 255} | AAAAAAAA |
| 130 | AddRoomDoor | rw | string | {"maxlen": 255} |  |
| 131 | DeleteRoomDoor | rw | string | {"maxlen": 255} |  |
| 132 | AppRemind | rw | string | {"maxlen": 255} | 0 |
| 133 | MapRoomInfo1 | rw | string | {"maxlen": 255} |  |
| 134 | MapRoomInfo2 | rw | string | {"maxlen": 255} |  |
| 135 | MapRoomInfo3 | rw | string | {"maxlen": 255} |  |
| 136 | CleanSettings | rw | string | {"maxlen": 255} | <redacted> |
| 137 | robot_info | rw | value | {"max": 1073741824, "min": 0, "scale": 0, "step": 1, "unit": ""} | `<redacted>` |
| 138 | language_select | rw | value | {"max": 255, "min": 0, "scale": 0, "step": 1, "unit": ""} | 55 |
| 139 | CleanAreaData | rw | string | {"maxlen": 255} |  |
| 140 | VirtualWallData | rw | string | {"maxlen": 255} |  |
| 141 | CleanPointData | rw | string | {"maxlen": 255} |  |
| 142 | ForbidZoneData | rw | string | {"maxlen": 255} |  |
| 143 | setting_disturb | rw | string | {"maxlen": 255} | <redacted> |
| 144 | user_map_name | rw | string | {"maxlen": 255} | `<redacted>` |
| 145 | pending_save_map | rw | value | {"max": 2073741824, "min": 0, "scale": 0, "step": 1, "unit": ""} | 0 |
| 146 | robot_position | rw | string | {"maxlen": 255} |  |
| 147 | mop_forbiden_data | rw | string | {"maxlen": 255} |  |
| 148 | wifi_info | ro | string | {"maxlen": 255} | `<redacted>` |
| 149 | y_mop | rw | bool | {} | True |
| 150 | clean_edge_brush | rw | bool | {} | False |
| 151 | clean_roll_brush | rw | bool | {} | False |
| 152 | clean_filter | rw | bool | {} | False |
| 153 | map_room_info_4 | rw | string | {"maxlen": 255} |  |
| 154 | map_room_info_5 | rw | string | {"maxlen": 255} |  |
| 155 | cleaning_efficiency | rw | enum | {"range": ["careful", "normal", "fast"]} | careful |
| 156 | continuation_time | ro | string | {"maxlen": 255} |  |
| 157 | maintenance | rw | string | {"maxlen": 255} | AAAADgAAAAAAAA4QAAAOEAAADhAAAAAAAAAAAAAAAAA= |
