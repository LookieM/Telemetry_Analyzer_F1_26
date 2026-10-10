import asyncio
import socket

from telemetria_server.config import Config, load_config
from telemetria_server.ingest import UdpIngest, forward_targets


def test_forward_targets_parsing_and_loop_guard():
    assert forward_targets("127.0.0.1:20778, 127.0.0.1:20779", 20777) == [("127.0.0.1", 20778), ("127.0.0.1", 20779)]
    assert forward_targets(["127.0.0.1:20778", "bad", "127.0.0.1:20777", "127.0.0.1:20778"], 20777) == [("127.0.0.1", 20778)]
    assert forward_targets("", 20777) == []


def test_toml_list_is_accepted(tmp_path):
    p = tmp_path / "telemetria.toml"
    p.write_text('forward_to = ["127.0.0.1:20778", "127.0.0.1:20779"]\n', encoding="utf-8")
    assert load_config(p).forward_to == "127.0.0.1:20778, 127.0.0.1:20779"


def test_packets_reach_every_forward_target(tmp_path):
    receivers = []
    for _ in range(2):
        r = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        r.bind(("127.0.0.1", 0))
        r.settimeout(2)
        receivers.append(r)
    targets = ", ".join(f"127.0.0.1:{r.getsockname()[1]}" for r in receivers)

    async def run():
        ing = UdpIngest(Config(record=True, udp_port=0, forward_to=targets, app_root=tmp_path))
        assert await ing.start()
        port = ing.transport.get_extra_info("sockname")[1]
        tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        for i in range(5):
            tx.sendto(b"packet-%d" % i, ("127.0.0.1", port))
        await asyncio.sleep(0.3)
        tx.close()
        await ing.stop()

    asyncio.run(run())
    for r in receivers:
        got = {r.recvfrom(100)[0] for _ in range(5)}
        r.close()
        assert got == {b"packet-%d" % i for i in range(5)}


def test_port_held_by_another_app_on_any_address_is_detected(tmp_path):
    from telemetria_server.ingest import udp_port_owner_free

    for holder_addr in ("0.0.0.0", "127.0.0.1"):
        holder = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        holder.bind((holder_addr, 0))
        port = holder.getsockname()[1]
        assert not udp_port_owner_free(port)

        async def run():
            ing = UdpIngest(Config(record=True, udp_port=port, app_root=tmp_path))
            ok = await ing.start()
            await ing.stop()
            return ok, ing.udp_error

        ok, err = asyncio.run(run())
        holder.close()
        assert not ok and "already used by another app" in err
