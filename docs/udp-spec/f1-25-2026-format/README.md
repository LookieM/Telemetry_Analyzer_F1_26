# F1 25 "2026 Season Pack" UDP format (packetFormat 2026) — reference headers

The `.h` files are the packed C struct definitions from
[MacManley/f1-26-udp](https://github.com/MacManley/f1-26-udp) v1.0.0 (MIT, see `LICENSE`),
copied here as the reference layout for `telemetria_server/udp/`. EA's own specification for this
format is posted on the EA forums ("F1® 25 : 2026 Season Pack UDP Specification").

Validated against a real capture from the game (F1 25 v1.26, `m_packetFormat = 2026`,
`m_gameYear = 25`, 2026-10-09): `struct_sizes.py` computes the packed size of every packet and all
14 packet types seen in the capture match byte for byte:

| id | packet | size |
|---:|---|---:|
| 0 | Motion | 1325 |
| 1 | Session | 926 |
| 2 | LapData | 1399 |
| 3 | Event | 45 |
| 4 | Participants | 1470 |
| 5 | CarSetups | 1233 |
| 6 | CarTelemetry | 1448 |
| 7 | CarStatus | 1445 |
| 10 | CarDamage | 1133 |
| 11 | SessionHistory | 1460 |
| 12 | TyreSets | 231 |
| 13 | MotionEx | 273 |
| 15 | LapPositions | 1231 |
| 16 | CarTelemetry2 (2026: active aero, overtake) | 269 |

Not seen in that capture: FinalClassification (1134), LobbyInfo (1062), TimeTrial (104).
Car arrays hold **24** cars in this format (22 in the 2025 format).

Run: `python docs/udp-spec/f1-25-2026-format/struct_sizes.py docs/udp-spec/f1-25-2026-format`
