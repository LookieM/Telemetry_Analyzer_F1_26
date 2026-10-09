# Live telemetry setup (F1 26, Windows)

## Game settings
Settings > Telemetry Settings:

- UDP Telemetry: **On**
- UDP Broadcast Mode: **Off**
- UDP IP Address: **127.0.0.1**
- UDP Port: **20777**
- UDP Send Rate: **60 Hz**
- UDP Format: **newest available**

## Record raw packets
```
python -m telemetria_server.capture
```
Writes `data/udp_captures/<YYYYmmdd-HHMMSS>.f1cap` and prints a status line every
5 s (packets/s, per-id counts, packetFormat, gameYear, sessionUID, frame-gap %).
Stop with Ctrl+C. Options: `--out FILE`, `--port N`, `--duration SECONDS`.

## Run Sim Racing Telemetry (SRT) in parallel
Only one app can bind a UDP port. Set SRT to listen on **20778** and forward:
```
python -m telemetria_server.capture --forward 127.0.0.1:20778
```
Packets are forwarded unchanged, so both tools receive the full stream.

## Inspect a capture
```
python -m telemetria_server.capture_info data/udp_captures/<file>.f1cap
```
Shows packetFormat/gameYear/versions, duration, packet count, session UIDs and,
per packet id, name, count, distinct sizes and frame-identifier gaps.
