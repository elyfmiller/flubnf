"""One-epidemic-per-season code must refuse, not answer, under COVID.

The failure this guards against is not a crash. It is a well-formed answer
about a peak that is one of two. Nothing downstream can tell that from a
correct answer, so the guard has to sit at the call, and there must be no way
to obtain an unmarked value under a bimodal-capable profile.
"""
from __future__ import annotations

import numpy as np
import pytest

from flubnf import unimodal_guard as ug
from flubnf.profiles import COVID, INFLUENZA

# One clean flu-shaped season: rise, peak, fall.
ONE_WAVE = np.array([5, 8, 14, 25, 48, 90, 150, 220, 260, 240, 180, 120,
                     70, 40, 22, 12, 7, 4], dtype=float)
# COVID 2025-26 in shape: a September wave LARGER than the January one, with a
# real trough between them. The order matters -- the argmax names the first.
TWO_WAVE = np.array([10, 20, 45, 90, 160, 230, 200, 120, 60, 30, 18, 12,
                     10, 14, 25, 55, 110, 180, 150, 90, 45, 22, 12, 8],
                    dtype=float)


class TestWaveCounting:
    def test_one_wave(self):
        assert ug.count_waves(ONE_WAVE) == 1

    def test_two_waves(self):
        assert ug.count_waves(TWO_WAVE) == 2

    def test_a_shoulder_is_not_a_second_wave(self):
        y = ONE_WAVE.copy()
        y[10] += 15                      # a bump, well under 40% of the peak
        assert ug.count_waves(y) == 1

    def test_empty_and_degenerate_inputs_do_not_raise(self):
        assert ug.count_waves([]) == 0
        assert ug.count_waves([3.0]) == 1
        assert ug.count_waves(np.zeros(20)) == 0


class TestRefusalUnderCovid:
    OPS = ("detect_phase", "place_centers", "season_peak",
           "shoulder_decomposition")

    def _call(self, op, profile, y, **kw):
        if op == "detect_phase":
            return ug.guarded_detect_phase(profile, y, **kw)
        if op == "place_centers":
            return ug.guarded_place_centers(profile, y, 3, **kw)
        if op == "season_peak":
            return ug.season_peak(profile, y, **kw)
        return ug.shoulder_decomposition(profile, y, **kw)

    @pytest.mark.parametrize("op", OPS)
    def test_refuses_under_covid_even_on_a_single_wave_series(self, op):
        """The refusal is about the PROFILE, not about this particular series.
        A one-wave stretch of a two-wave disease is still a partial season."""
        with pytest.raises(ug.BimodalProfileError):
            self._call(op, COVID, ONE_WAVE)

    @pytest.mark.parametrize("op", OPS)
    def test_acknowledgement_yields_a_marked_value_not_a_clean_one(self, op):
        g = self._call(op, COVID, TWO_WAVE, acknowledge_bimodal=True)
        assert g.value is not None
        assert g.unimodal_assumption_violated is True
        assert g.mark and "MARKED" in g.mark
        assert g.profile_key == "covid"
        assert g.waves_detected == 2

    @pytest.mark.parametrize("op", OPS)
    def test_non_strict_mode_returns_none_rather_than_a_number(self, op):
        g = self._call(op, COVID, TWO_WAVE, strict=False)
        assert g.value is None
        assert bool(g) is False
        assert "REFUSED" in g.mark


class TestInfluenzaUnchanged:
    def test_phase_matches_the_unguarded_function_exactly(self):
        from flubnf.phase import detect_phase
        g = ug.guarded_detect_phase(INFLUENZA, ONE_WAVE)
        assert g.value == detect_phase(ONE_WAVE)
        assert g.unimodal_assumption_violated is False
        assert g.mark is None

    def test_centers_match_the_unguarded_function_exactly(self):
        from flubnf.centers import place_centers
        g = ug.guarded_place_centers(INFLUENZA, ONE_WAVE, 3)
        assert g.value == place_centers(ONE_WAVE, 3)
        assert g.unimodal_assumption_violated is False

    def test_peak_is_the_argmax(self):
        g = ug.season_peak(INFLUENZA, ONE_WAVE)
        assert g.value.index == int(np.argmax(ONE_WAVE))
        assert g.value.value == pytest.approx(ONE_WAVE.max())

    def test_shoulder_split_is_the_expected_one(self):
        g = ug.shoulder_decomposition(INFLUENZA, ONE_WAVE)
        i = int(np.argmax(ONE_WAVE))
        assert g.value.peak_index == i
        assert g.value.rise == (0, i)
        assert g.value.shoulder == (i, len(ONE_WAVE) - 1)

    def test_a_two_wave_flu_season_is_still_marked(self):
        """The assumption is about the series too. This is the second-wave case
        fringe_cases.py already flags for influenza."""
        g = ug.season_peak(INFLUENZA, TWO_WAVE)
        assert g.value is not None            # influenza never refuses
        assert g.unimodal_assumption_violated is True
        assert g.waves_detected == 2


class TestWaveAwareReplacement:
    def test_all_peaks_finds_both_and_needs_no_guard(self):
        peaks = ug.all_peaks(TWO_WAVE)
        assert len(peaks) == 2
        assert peaks[0].index < peaks[1].index
        assert peaks[0].value == pytest.approx(TWO_WAVE.max())

    def test_all_peaks_carries_dates_when_given(self):
        dates = [f"2025-{1 + i // 4:02d}-{1 + (i % 4) * 7:02d}"
                 for i in range(len(TWO_WAVE))]
        peaks = ug.all_peaks(TWO_WAVE, dates)
        assert all(p.date and len(p.date) == 10 for p in peaks)

    def test_the_argmax_names_only_one_of_the_two(self):
        """The concrete reason season_peak is a category error under COVID."""
        g = ug.season_peak(COVID, TWO_WAVE, acknowledge_bimodal=True)
        peaks = ug.all_peaks(TWO_WAVE)
        assert g.value.index == peaks[0].index
        assert peaks[1].value > 0.5 * peaks[0].value


class TestGuardReport:
    def test_covid_report_says_it_refuses(self):
        r = ug.guard_report(COVID)
        assert r["bimodal_capable"] is True
        assert "refuse" in r["behaviour"]
        assert set(r["guarded_operations"]) == {
            "detect_phase", "place_centers", "season_peak",
            "shoulder_decomposition"}

    def test_influenza_report_says_it_passes_through(self):
        r = ug.guard_report(INFLUENZA)
        assert r["bimodal_capable"] is False
        assert "pass through" in r["behaviour"]
