"""The satellite table and the summary helpers in gnss_state.c."""

from __future__ import annotations


def test_init_marks_everything_unknown(state, lib):
    assert state.hdop == 0xFFFF and state.gdop == 0xFFFF
    assert state.diff_age_ds == -1 and state.diff_station == -1
    assert state.antenna == lib.GNSS_ANT_NOT_REPORTED
    assert state.n_sats == 0


def test_sat_is_found_again_not_duplicated(state, lib):
    a = lib.gnss_sat(state, lib.GNSS_GPS, 12)
    a.cno = 40
    b = lib.gnss_sat(state, lib.GNSS_GPS, 12)
    assert b.cno == 40
    assert state.n_sats == 1
    lib.gnss_sat(state, lib.GNSS_GALILEO, 12)  # same number, other constellation
    assert state.n_sats == 2


def test_new_sat_has_unknown_position(state, lib):
    sat = lib.gnss_sat(state, lib.GNSS_GPS, 1)
    assert sat.elev == -91 and sat.azim == -1 and sat.cno == 0 and not sat.used


def test_sats_not_reported_for_two_epochs_are_dropped(state, lib):
    lib.gnss_sat(state, lib.GNSS_GPS, 1)
    lib.gnss_sat(state, lib.GNSS_GPS, 2)
    lib.gnss_new_epoch(state)
    assert state.n_sats == 2  # both seen in the previous epoch: kept
    lib.gnss_sat(state, lib.GNSS_GPS, 2)  # 2 seen again, 1 not
    lib.gnss_new_epoch(state)
    assert [state.sats[i].svid for i in range(state.n_sats)] == [2]
    lib.gnss_new_epoch(state)
    assert state.n_sats == 0


def test_full_table_returns_null(ffi, state, lib):
    for svid in range(1, lib.GNSS_MAX_SATS + 1):
        assert lib.gnss_sat(state, lib.GNSS_BEIDOU, svid) != ffi.NULL
    assert lib.gnss_sat(state, lib.GNSS_GPS, 1) == ffi.NULL


def test_full_table_makes_room_by_pruning(ffi, state, lib):
    for svid in range(1, lib.GNSS_MAX_SATS + 1):
        lib.gnss_sat(state, lib.GNSS_BEIDOU, svid)
    lib.gnss_new_epoch(state)
    lib.gnss_new_epoch(state)  # every satellite is now stale, but not yet pruned by a lookup
    state.n_sats = lib.GNSS_MAX_SATS
    assert lib.gnss_sat(state, lib.GNSS_GPS, 1) != ffi.NULL
    assert state.n_sats == 1


def test_counts(state, lib):
    for gnss, svid, used in ((lib.GNSS_GPS, 1, True), (lib.GNSS_GPS, 2, False), (lib.GNSS_GALILEO, 3, True)):
        lib.gnss_sat(state, gnss, svid).used = used
    assert lib.gnss_count_sats(state, lib.GNSS_UNKNOWN, False) == 3
    assert lib.gnss_count_sats(state, lib.GNSS_UNKNOWN, True) == 2
    assert lib.gnss_count_sats(state, lib.GNSS_GPS, False) == 2
    assert lib.gnss_count_sats(state, lib.GNSS_GPS, True) == 1
    assert lib.gnss_count_sats(state, lib.GNSS_BEIDOU, False) == 0


def test_cno_stats_cover_used_satellites_only(ffi, state, lib):
    for svid, cno, used in ((1, 30, True), (2, 45, True), (3, 50, False), (4, 0, True)):
        sat = lib.gnss_sat(state, lib.GNSS_GPS, svid)
        sat.cno, sat.used = cno, used
    lo, avg, hi = ffi.new("uint8_t *"), ffi.new("uint8_t *"), ffi.new("uint8_t *")
    assert lib.gnss_cno_stats(state, lo, avg, hi) == 2
    assert (lo[0], avg[0], hi[0]) == (30, 38, 45)  # 37.5 rounds up


def test_cno_stats_with_nothing_used(ffi, state, lib):
    lo, avg, hi = ffi.new("uint8_t *"), ffi.new("uint8_t *"), ffi.new("uint8_t *")
    assert lib.gnss_cno_stats(state, lo, avg, hi) == 0
    assert (lo[0], avg[0], hi[0]) == (0, 0, 0)


def test_names(ffi, lib):
    assert ffi.string(lib.gnss_constellation_name(lib.GNSS_GLONASS)) == b"GLONASS"
    assert ffi.string(lib.gnss_constellation_name(200)) == b"Unknown"
    assert lib.gnss_constellation_letter(lib.GNSS_BEIDOU) == b"C"
    assert lib.gnss_constellation_letter(lib.GNSS_QZSS) == b"J"
