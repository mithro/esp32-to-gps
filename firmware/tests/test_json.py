"""State JSON and Home Assistant discovery in gnss_json.c.

Every discovery template is rendered with Jinja2, the engine Home Assistant
uses, against state JSON produced from the real capture, so a template
naming a key the state does not have fails here, not in Home Assistant.
"""

from __future__ import annotations

import json

import jinja2
import pytest

from conftest import FIXTURES

UID = "gps_a0b1c2d3e4f5"


def run_capture(ffi, lib, state, name: str) -> None:
    st = ffi.new("gnss_stream_t *")
    lib.gnss_stream_init(st)
    for b in (FIXTURES / name).read_bytes():
        t = lib.gnss_stream_byte(st, b)
        if t == lib.GNSS_FRAME_NMEA:
            lib.gnss_nmea_parse(state, ffi.cast("char *", st.buf))
        elif t == lib.GNSS_FRAME_UBX:
            lib.gnss_ubx_parse(state, st.buf[0], st.buf[1], st.buf + 4, st.ubx_len)


@pytest.fixture
def keep(ffi):
    """Keeps cffi allocations alive while structs point at them."""
    return []


def extra(ffi, lib, keep, **kw):
    x = ffi.new("gnss_extra_t *")
    r = ffi.new("gnss_rtcm_t *")
    lib.gnss_rtcm_init(r)
    strs = {k: ffi.new("char[]", kw.pop(k, "").encode()) for k in ("corr_mount", "corr_error")}
    keep.extend([x, r, *strs.values()])
    x.rtcm = r
    x.corr_mount, x.corr_error = strs["corr_mount"], strs["corr_error"]
    x.corr_age_s, x.data_age_s = kw.pop("corr_age_s", -1), kw.pop("data_age_s", 0)
    x.baud = kw.pop("baud", 38400)
    for k, v in kw.items():
        setattr(x, k, v)
    return x, r


def state_json(ffi, lib, state, x, size=4096) -> dict:
    out = ffi.new(f"char[{size}]")
    n = lib.gnss_json_state(out, size, state, x)
    assert n > 0
    return json.loads(ffi.string(out).decode())


def sats_json(ffi, lib, state) -> dict:
    out = ffi.new("char[8192]")
    n = lib.gnss_json_sats(out, 8192, state)
    assert n > 0
    return json.loads(ffi.string(out).decode())


def device(ffi, keep):
    d = ffi.new("gnss_hass_device_t *")
    vals = dict(uid=UID, name="GPS bench", topic="tele/gps_bench/", lwt="tele/gps_bench/LWT",
                model="MAX-M10S", sw="15.6.0.2(esp32-to-gps)", url="http://10.1.90.42/")
    for k, v in vals.items():
        c = ffi.new("char[]", v.encode())
        keep.append(c)
        setattr(d, k, c)
    keep.append(d)
    return d


def configs(ffi, lib, keep):
    dev = device(ffi, keep)
    topic, payload = ffi.new("char[256]"), ffi.new("char[2048]")
    out = []
    for i in range(lib.gnss_hass_count()):
        n = lib.gnss_hass_config(i, dev, topic, 256, payload, 2048)
        assert n > 0, i
        out.append((ffi.string(topic).decode(), json.loads(ffi.string(payload).decode())))
    return out


def render(template: str, value: dict) -> str:
    env = jinja2.Environment()
    return env.from_string(template).render(value_json=value)


# -- state JSON ---------------------------------------------------------------

def test_state_from_real_nmea_capture(ffi, lib, state, keep):
    run_capture(ffi, lib, state, "max-m10s-nmea.bin")
    x, _ = extra(ffi, lib, keep, corr_mount="ADDE_RTCM3")
    j = state_json(ffi, lib, state, x)
    assert j["Time"].startswith("2026-10-04T") and j["Time"].endswith("Z")
    assert j["Fix"] == "3D" and j["Quality"] == "GNSS"
    assert j["Lat"] == pytest.approx(-34.9285, abs=1e-4) and j["Lon"] == pytest.approx(138.6007, abs=1e-4)
    assert j["SatsUsed"] == 16 and j["SatsInView"] == 36
    assert j["Constellations"]["GPS"] == {"InView": 11, "Used": 7}
    assert j["Constellations"]["GLONASS"] == {"InView": 0, "Used": 0}
    assert j["HDOP"] == 0.91 and j["GDOP"] is None  # NMEA does not carry GDOP
    assert 0 < j["CNo"]["Min"] <= j["CNo"]["Avg"] <= j["CNo"]["Max"]
    assert j["DiffAge"] is None and j["Corrections"]["Mount"] == "ADDE_RTCM3"
    assert j["Receiver"]["Model"] is None  # never identified in a passive capture
    assert j["Health"]["NMEA"] == 684


def test_state_without_fix_is_null_not_zero(ffi, lib, state, keep):
    run_capture(ffi, lib, state, "max-m10s-ubx.bin")  # pluto: no fix
    x, _ = extra(ffi, lib, keep)
    j = state_json(ffi, lib, state, x)
    assert j["Fix"] == "No fix"
    for k in ("Lat", "Lon", "AltMSL", "HAcc", "VAcc", "Speed", "Course"):
        assert j[k] is None, k
    assert j["GDOP"] is not None  # NAV-DOP reports DOPs even without a fix


def test_state_fixed_point_formatting(ffi, lib, state, keep):
    state.position_valid = True
    state.lat_e7, state.lon_e7 = -5, 1234567890
    state.alt_valid, state.alt_msl_mm = True, -7
    x, _ = extra(ffi, lib, keep)
    out = ffi.new("char[4096]")
    lib.gnss_json_state(out, 4096, state, x)
    text = ffi.string(out).decode()
    assert '"Lat":-0.0000005' in text and '"Lon":123.4567890' in text and '"AltMSL":-0.007' in text


def test_state_corrections(ffi, lib, state, keep):
    x, r = extra(ffi, lib, keep, corr_state=lib.GNSS_CORR_CONNECTED, corr_mount="ADDE_RTCM3", corr_age_s=2)
    data = (FIXTURES / "ntrip-adde-rtcm3.bin").read_bytes()
    lib.gnss_rtcm_feed(r, data, len(data))
    state.rtcm_used, state.rtcm_failed = 40, 1
    c = state_json(ffi, lib, state, x)["Corrections"]
    assert c["State"] == "Connected" and c["Age"] == 2 and c["Frames"] == 77 and c["Used"] == 40
    assert c["Types"].split(",")[0].isdigit() and "1077" in c["Types"].split(",")
    assert isinstance(c["Station"], int)


def test_state_too_big_for_buffer(ffi, lib, state, keep):
    x, _ = extra(ffi, lib, keep)
    out = ffi.new("char[100]")
    assert lib.gnss_json_state(out, 100, state, x) == 0


def test_state_with_a_full_satellite_table_fits_the_driver_buffer(ffi, lib, state, keep):
    """The driver publishes from 2 KB (state) and 4 KB (satellites) buffers."""
    for svid in range(1, lib.GNSS_MAX_SATS + 1):
        sat = lib.gnss_sat(state, lib.GNSS_BEIDOU, svid)
        sat.elev, sat.azim, sat.cno, sat.used = -45, 359, 45, True
    x, r = extra(ffi, lib, keep, corr_mount="ADDE_RTCM3", corr_error="x" * 40, corr_age_s=99999)
    for i in range(lib.GNSS_RTCM_TYPES):
        r.types[i] = 4094
    r.n_types = lib.GNSS_RTCM_TYPES
    for f in ("model", "sw_version", "hw_version", "protocol"):
        ffi.memmove(getattr(state, f), b"M" * 31, 31)
    out = ffi.new("char[2048]")
    assert lib.gnss_json_state(out, 2048, state, x) > 0
    out = ffi.new("char[4096]")
    assert lib.gnss_json_sats(out, 4096, state) > 0


# -- satellites JSON -------------------------------------------------------------

def test_sats_json(ffi, lib, state):
    run_capture(ffi, lib, state, "max-m10s-nmea.bin")
    j = sats_json(ffi, lib, state)
    assert j["InView"] == len(j["Sats"]) == 36 and j["Used"] == 16
    ids = [s[0] for s in j["Sats"]]
    assert len(set(ids)) == len(ids)
    for sid, name, elev, azim, cno, used in j["Sats"]:
        assert sid[0] in "GSECJRI" and name in ("GPS", "SBAS", "Galileo", "BeiDou", "QZSS", "GLONASS", "NavIC")
        assert elev is None or -90 <= elev <= 90
        assert azim is None or 0 <= azim < 360
        assert j["CNo"][sid] == cno and isinstance(used, bool)


# -- discovery ------------------------------------------------------------------

def test_every_entity_has_a_unique_id_and_topic(ffi, lib, keep):
    cfgs = configs(ffi, lib, keep)
    assert len(cfgs) == lib.gnss_hass_count() == 66
    assert len({c["uniq_id"] for _, c in cfgs}) == len(cfgs)
    assert len({t for t, _ in cfgs}) == len(cfgs)
    for topic, c in cfgs:
        comp = topic.split("/")[1]
        assert topic == f"homeassistant/{comp}/{UID}/{c['uniq_id'][len(UID) + 1:]}/config"
        assert c["dev"]["ids"] == [UID] and c["dev"]["mdl"] == "MAX-M10S" and c["dev"]["cu"] == "http://10.1.90.42/"
        assert c["avty_t"] == "tele/gps_bench/LWT"


def test_every_template_renders_against_real_state(ffi, lib, state, keep):
    run_capture(ffi, lib, state, "max-m10s-nmea.bin")
    x, _ = extra(ffi, lib, keep, corr_mount="ADDE_RTCM3")
    gnss = state_json(ffi, lib, state, x)
    sats = sats_json(ffi, lib, state)
    for topic, c in configs(ffi, lib, keep):
        comp = topic.split("/")[1]
        if comp == "device_tracker":
            attrs = json.loads(render(c["json_attr_tpl"], gnss))
            assert attrs == {"latitude": gnss["Lat"], "longitude": gnss["Lon"], "gps_accuracy": gnss["HAcc"]}
            continue
        value = sats if c["stat_t"].endswith("GNSS_SATS") else gnss
        out = render(c["val_tpl"], value)
        if comp == "binary_sensor":
            assert out in ("ON", "OFF"), c["name"]
        elif "unit_of_meas" in c or "stat_cla" in c:
            assert out == "None" or float(out) == float(out), (c["name"], out)
        else:
            assert out, c["name"]


def test_templates_render_with_no_data_at_all(ffi, lib, state, keep):
    """Before the receiver says anything: every entity unknown, nothing errors."""
    x, _ = extra(ffi, lib, keep, data_age_s=-1)
    gnss = state_json(ffi, lib, state, x)
    sats = sats_json(ffi, lib, state)
    for topic, c in configs(ffi, lib, keep):
        if "val_tpl" in c:
            render(c["val_tpl"], sats if c["stat_t"].endswith("GNSS_SATS") else gnss)
        else:
            assert render(c["json_attr_tpl"], gnss) == "{}"


def test_tracker_and_satellites_sensor(ffi, lib, keep):
    cfgs = {c["uniq_id"][len(UID) + 1:]: (t, c) for t, c in configs(ffi, lib, keep)}
    t, c = cfgs["location"]
    assert t.startswith("homeassistant/device_tracker/") and c["src_type"] == "gps"
    assert c["json_attr_t"] == "tele/gps_bench/GNSS" and "stat_t" not in c
    t, c = cfgs["satellites"]
    assert c["stat_t"] == c["json_attr_t"] == "tele/gps_bench/GNSS_SATS"


def test_units_and_classes_are_ones_home_assistant_accepts(ffi, lib, keep):
    for _, c in configs(ffi, lib, keep):
        if c.get("dev_cla") == "distance":
            assert c["unit_of_meas"] == "m"
        if c.get("dev_cla") == "speed":
            assert c["unit_of_meas"] == "m/s"
        if c.get("dev_cla") == "duration":
            assert c["unit_of_meas"] == "s"
        if c.get("dev_cla") == "data_size":
            assert c["unit_of_meas"] == "B"
        if c.get("dev_cla") == "timestamp":
            assert "unit_of_meas" not in c and "stat_cla" not in c
        assert c.get("stat_cla") in (None, "measurement", "total_increasing")
        assert c.get("ent_cat") in (None, "diagnostic")


def test_per_satellite_entity(ffi, lib, state, keep):
    dev = device(ffi, keep)
    topic, payload = ffi.new("char[256]"), ffi.new("char[2048]")
    n = lib.gnss_hass_sat_config(lib.GNSS_GALILEO, 7, False, dev, topic, 256, payload, 2048)
    c = json.loads(ffi.string(payload).decode())
    assert n > 0 and ffi.string(topic) == f"homeassistant/sensor/{UID}/sat_E07/config".encode()
    assert c["name"] == "Galileo 7 C/N0" and c["exp_aft"] == 120
    lib.gnss_sat(state, lib.GNSS_GALILEO, 7).cno = 33
    assert render(c["val_tpl"], sats_json(ffi, lib, state)) == "33"
    lib.gnss_state_init(state)
    assert render(c["val_tpl"], sats_json(ffi, lib, state)) == "None"  # out of view: unknown
    n = lib.gnss_hass_sat_config(lib.GNSS_GALILEO, 7, True, dev, topic, 256, payload, 2048)
    assert n == 0 and ffi.string(payload) == b"" and b"sat_E07" in ffi.string(topic)


def test_config_bad_index_and_small_buffers(ffi, lib, keep):
    dev = device(ffi, keep)
    topic, payload = ffi.new("char[256]"), ffi.new("char[2048]")
    assert lib.gnss_hass_config(-1, dev, topic, 256, payload, 2048) == 0
    assert lib.gnss_hass_config(lib.gnss_hass_count(), dev, topic, 256, payload, 2048) == 0
    assert lib.gnss_hass_config(0, dev, topic, 10, payload, 2048) == 0
    assert lib.gnss_hass_config(0, dev, topic, 256, payload, 50) == 0


def test_every_config_fits_the_driver_buffer(ffi, lib, keep):
    """The driver builds discovery payloads in a 1 KB buffer."""
    dev = device(ffi, keep)
    topic, payload = ffi.new("char[256]"), ffi.new("char[1024]")
    for i in range(lib.gnss_hass_count()):
        assert lib.gnss_hass_config(i, dev, topic, 256, payload, 1024) > 0, i
