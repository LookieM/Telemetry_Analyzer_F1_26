# Graph Report - Telemetria F1 26  (2026-11-16)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 3996 nodes · 11878 edges · 133 communities (125 shown, 8 thin omitted)
- Extraction: 97% EXTRACTED · 3% INFERRED · 0% AMBIGUOUS · INFERRED: 314 edges (avg confidence: 0.88)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `1601d91e`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- Community 0
- Community 1
- Community 2
- Community 3
- Community 4
- Community 5
- Community 6
- Community 7
- Community 8
- Community 9
- Community 10
- Community 11
- Community 12
- Community 13
- Community 14
- Community 15
- Community 16
- Community 17
- Community 18
- Community 19
- Community 20
- Community 21
- Community 22
- Community 23
- Community 24
- Community 25
- Community 26
- Community 27
- Community 28
- Community 29
- Community 30
- Community 31
- Community 32
- Community 33
- Community 34
- Community 35
- Community 36
- Community 37
- Community 38
- Community 39
- Community 40
- Community 41
- Community 42
- Community 43
- Community 44
- Community 45
- Community 46
- Community 47
- Community 48
- Community 49
- Community 50
- Community 51
- Community 52
- Community 53
- Community 54
- Community 55
- Community 56
- Community 57
- Community 58
- Community 59
- Community 60
- Community 61
- Community 62
- Community 63
- Community 64
- Community 65
- Community 66
- Community 67
- Community 68
- Community 69
- Community 70
- Community 71
- Community 72
- Community 73
- Community 74
- Community 75
- Community 76
- Community 77
- Community 78
- Community 79
- Community 80
- Community 81
- Community 82
- Community 83
- Community 84
- Community 85
- Community 86
- Community 87
- Community 88
- Community 89
- Community 90
- Community 91
- Community 92
- Community 94
- Community 95
- Community 96
- Community 97
- Community 98
- Community 99
- Community 100
- Community 101
- Community 102
- Community 103
- Community 104
- Community 105
- Community 106
- Community 107
- Community 108
- Community 109
- Community 110
- Community 111
- Community 112
- Community 113
- Community 114
- Community 115
- Community 116
- Community 117
- Community 118
- Community 119
- Community 120
- Community 121
- Community 122
- Community 123
- Community 124
- Community 125
- Community 126
- Community 127
- Community 129
- Community 130
- Community 131

## God Nodes (most connected - your core abstractions)
1. `connect()` - 103 edges
2. `PacketSessionData` - 97 edges
3. `normalize_track_name()` - 95 edges
4. `render_analysis()` - 78 edges
5. `en()` - 69 edges
6. `Engineer` - 64 edges
7. `LiveEngine` - 59 edges
8. `to_jsonable()` - 54 edges
9. `get_lap()` - 54 edges
10. `build_lap_summary()` - 46 edges

## Surprising Connections (you probably didn't know these)
- `Li()` --indirect_call--> `g()`  [INFERRED]
  telemetry/ui/assets/uplot/uPlot.iife.min.js → frontend/src/lib/baseline.test.ts
- `test_confirm_can_override_the_ranking()` --uses--> `EngineerError`  [INFERRED]
  tests/udp/test_duel.py → telemetria_server/live/engineer.py
- `test_question_only_in_garage_after_all_contestants()` --uses--> `EngineerError`  [INFERRED]
  tests/udp/test_duel.py → telemetria_server/live/engineer.py
- `test_rank_wrong_order_and_wrong_phase()` --uses--> `EngineerError`  [INFERRED]
  tests/udp/test_duel.py → telemetria_server/live/engineer.py
- `test_skip_contestant_needs_two_left()` --uses--> `EngineerError`  [INFERRED]
  tests/udp/test_duel.py → telemetria_server/live/engineer.py

## Import Cycles
- None detected.

## Communities (133 total, 8 thin omitted)

### Community 1 - "Community 1"
Cohesion: 0.07
Nodes (78): qs(), useAllocation(), useClearAllocation(), useClearOverrides(), useCoach(), useCompoundModel(), useDeleteSession(), useImportFile() (+70 more)

### Community 2 - "Community 2"
Cohesion: 0.05
Nodes (79): useBalance(), useCompare(), useCorners(), useLapExtras(), useMap(), useRebuildCorners(), LapExtra, MapPayload (+71 more)

### Community 3 - "Community 3"
Cohesion: 0.07
Nodes (41): _color_payload(), lap_map_payload(), map_axes(), _values(), active_aero_plot(), active_aero_profile_bars(), _add_corner_vlines(), corner_delta_bars() (+33 more)

### Community 4 - "Community 4"
Cohesion: 0.04
Nodes (70): api, ApiError, duelApi, request(), useClearTyreSets(), useOverrides(), useSaveTyreSets(), AllocationEntry (+62 more)

### Community 5 - "Community 5"
Cohesion: 0.07
Nodes (66): useNameSetup(), useRunDuel(), useSetBaseline(), useTrackBaseline(), useTrackProfile(), useTrackSetups(), DuelBalance, DuelContestant (+58 more)

### Community 6 - "Community 6"
Cohesion: 0.07
Nodes (14): LiveEngine, _ms(), _text(), LiveState, session_type_name(), track_name(), _engineer_params_for_baseline(), test_a_failing_recorder_never_breaks_the_engine() (+6 more)

### Community 7 - "Community 7"
Cohesion: 0.08
Nodes (52): all_settled(), ensure_engineer_schema(), _iso(), list_tests(), save_test(), settled_for(), test_baseline_from_engineer_test(), Car (+44 more)

### Community 8 - "Community 8"
Cohesion: 0.07
Nodes (39): temp_kind(), is_slick(), pa_to_psi(), _assume(), _cached_race_stats(), _cold_pressures(), default_wear_limit(), DegFit (+31 more)

### Community 9 - "Community 9"
Cohesion: 0.07
Nodes (60): baselineApi, engineerApi, EngineerResult, EngineerVariant, EngineerView, DuelStart(), Confirm(), EngineerCard() (+52 more)

### Community 10 - "Community 10"
Cohesion: 0.10
Nodes (10): _disp(), Engineer, EngineerError, _f(), _Pair, _text(), _finished(), test_next_program_starts_from_the_settled_values() (+2 more)

### Community 11 - "Community 11"
Cohesion: 0.08
Nodes (37): plan_json(), model_payload(), actual_plan(), apply_overrides(), clear_overrides(), CompoundSpec, default_params(), _diff() (+29 more)

### Community 12 - "Community 12"
Cohesion: 0.06
Nodes (53): ChannelsPayload, ComparePayload, InventoryRow, OptimisePayload, ReviewJson, Series, TyresPayload, DELTA (+45 more)

### Community 13 - "Community 13"
Cohesion: 0.08
Nodes (24): _best_lengths(), _cost_to_go(), _Costs, optimise(), _plan_cost(), plan_from_state(), RaceParams, _Slot (+16 more)

### Community 14 - "Community 14"
Cohesion: 0.06
Nodes (33): fields_size(), matching_brace(), size_of(), delta_at(), _classify_laps(), backfill_session_tags(), infer_tags(), state_from_telemetry() (+25 more)

### Community 15 - "Community 15"
Cohesion: 0.09
Nodes (29): Inputs, allocation_payload(), primary_tyre_temp(), Allocation, softness(), manual_specs(), _cached_model(), CompoundModel (+21 more)

### Community 16 - "Community 16"
Cohesion: 0.10
Nodes (33): cached_session_df(), format_bytes(), format_lap_time(), library_maintenance(), main(), _open_garage_for_track(), pick_session(), pin_cursor() (+25 more)

### Community 17 - "Community 17"
Cohesion: 0.08
Nodes (25): setup_fingerprints(), _alt(), _build_specs(), _confidence_order(), _halve(), _q(), _Spec, correct_groups() (+17 more)

### Community 18 - "Community 18"
Cohesion: 0.10
Nodes (28): coach_feed_for_session(), CoachItem, _coast_conflict(), collect_coach_items(), collect_session_coach_items(), _corner_to_item(), dedupe_and_resolve(), _diagnosis_items() (+20 more)

### Community 19 - "Community 19"
Cohesion: 0.08
Nodes (17): main(), summarize(), main(), _parse_hostport(), run_capture(), _status_line(), main(), replay() (+9 more)

### Community 20 - "Community 20"
Cohesion: 0.11
Nodes (23): render_2026_channels_panel(), _tip_css(), active_aero_by_distance(), channels_2026_insights(), compare_active_aero(), compare_ers_profiles(), enrich_2026_channels(), enrich_ers() (+15 more)

### Community 21 - "Community 21"
Cohesion: 0.11
Nodes (21): lap_or_404(), load_columns(), session_or_404(), _balance_block(), _best_lap(), rebuild_corners(), RebuildBody, session_balance_view() (+13 more)

### Community 22 - "Community 22"
Cohesion: 0.10
Nodes (25): _base_url(), _config(), default_geometry(), Geometry, GeometryTracker, initial_geometry(), load_state(), main() (+17 more)

### Community 23 - "Community 23"
Cohesion: 0.06
Nodes (22): damage_loss(), LapRecord, delta(), RefLap, _window(), wing_advice(), _arr(), damage_row() (+14 more)

### Community 24 - "Community 24"
Cohesion: 0.12
Nodes (28): lifespan(), compact_dataframe(), connect(), db_path(), delete_session(), ensure_session_meta_schema(), _extra_channels(), extract_track_outline() (+20 more)

### Community 25 - "Community 25"
Cohesion: 0.09
Nodes (23): _brake_onsets(), compare_brake_markers(), generate_insights(), _pct(), align_laps(), _apply_relative_probable_mask(), _build_lap_summary(), _col() (+15 more)

### Community 26 - "Community 26"
Cohesion: 0.13
Nodes (3): _Contestant, Duel, _f()

### Community 27 - "Community 27"
Cohesion: 0.09
Nodes (21): fuel_corrected_time(), _aggregate_balance(), best_run(), _build_run(), _lap_fuel(), Run, runs_frame(), _slope() (+13 more)

### Community 28 - "Community 28"
Cohesion: 0.07
Nodes (19): main(), copy_library_db(), client(), empty_client(), lib_root(), race_id(), _baseline(), hun() (+11 more)

### Community 29 - "Community 29"
Cohesion: 0.09
Nodes (37): useGeneratedSetup(), BaselineSource, Confidence, EngineerBaselineOffer, GarageValue, GeneratedDisplayItem, GeneratedEntry, GeneratedEvidence (+29 more)

### Community 30 - "Community 30"
Cohesion: 0.12
Nodes (28): _aero_vs_typical(), _apply(), _apply_mixed(), _apply_oversteer(), _apply_understeer(), _brake_fix(), build_setup_from_practice(), BuiltSetup (+20 more)

### Community 31 - "Community 31"
Cohesion: 0.10
Nodes (19): analyze_lap_corners(), compare_corners(), corner_at_distance(), corner_loss_summary(), _corner_phase_metrics(), CornerDef, detect_corners_from_lap(), _first_crossing() (+11 more)

### Community 32 - "Community 32"
Cohesion: 0.05
Nodes (35): LapData, m_carPosition, m_cornerCuttingWarnings, m_currentLapInvalid, m_currentLapNum, m_currentLapTimeInMS, m_deltaToCarInFrontInMinutesPart, m_deltaToCarInFrontInMSPart (+27 more)

### Community 33 - "Community 33"
Cohesion: 0.09
Nodes (15): legacy_live_to_srt(), full_throttle_mask(), lap_grid(), _minima(), _runs(), _smooth(), callouts(), corner_phases() (+7 more)

### Community 34 - "Community 34"
Cohesion: 0.08
Nodes (8): _Protocol, SessionManager, SessionRecorder, test_checkpoint_written_each_lap_and_recovered(), test_manager_ends_session_on_idle_and_uid_change(), test_uid_zero_packets_do_not_split_or_reset_a_session(), recorder(), test_ingest_into_temp_library()

### Community 35 - "Community 35"
Cohesion: 0.12
Nodes (22): garage_from_raw(), is_raw_setup(), _num(), out_of_range(), raw_asymmetry(), to_garage(), _backup_db(), reread_library_setups() (+14 more)

### Community 36 - "Community 36"
Cohesion: 0.07
Nodes (18): create_app(), SPAStaticFiles, test_backend_does_not_import_streamlit(), test_delete_session(), test_serialization(), test_session_detail(), test_static_mount_only_with_dist(), test_token_middleware() (+10 more)

### Community 37 - "Community 37"
Cohesion: 0.13
Nodes (14): Config, forward_targets(), _hostport(), udp_port_owner_free(), UdpIngest, recover_checkpoints(), test_forward_targets_parsing_and_loop_guard(), test_packets_reach_every_forward_target() (+6 more)

### Community 38 - "Community 38"
Cohesion: 0.14
Nodes (24): Application, best_verified_setup(), _direction(), ensure_log_schema(), evaluate_all(), evaluate_track(), followup_entries(), get_recommendations() (+16 more)

### Community 39 - "Community 39"
Cohesion: 0.09
Nodes (24): Al(), B(), bt(), Cl(), Dl(), dt(), Ai(), Ft() (+16 more)

### Community 40 - "Community 40"
Cohesion: 0.13
Nodes (20): tracks(), clear_allocation(), ensure_allocation_schema(), get_allocation(), get_game_tyres(), roles_from_codes(), save_game_tyres(), set_allocation() (+12 more)

### Community 41 - "Community 41"
Cohesion: 0.13
Nodes (36): De(), en(), An(), bi(), C(), Ce(), ci(), Di() (+28 more)

### Community 42 - "Community 42"
Cohesion: 0.08
Nodes (6): import_session(), PathImport, _run(), compound_model(), default_limit(), session_tyres()

### Community 43 - "Community 43"
Cohesion: 0.12
Nodes (25): AnswerIn, _command(), ConfirmIn, duel_confirm(), duel_rank(), duel_skip(), duel_start(), duel_stop() (+17 more)

### Community 44 - "Community 44"
Cohesion: 0.12
Nodes (14): store_live_duel(), backfill_setup_fingerprints(), compute_setup_fingerprint(), diff_setups(), fingerprint_for_session(), format_setup_delta(), list_track_sessions(), mech_fingerprint() (+6 more)

### Community 45 - "Community 45"
Cohesion: 0.14
Nodes (20): balance_phases(), _corner_of(), has_slip_channels(), lap_balance(), session_balance(), _balance_of(), make_frame(), test_front_slipping_more_than_rear_is_positive_understeer_in_degrees() (+12 more)

### Community 46 - "Community 46"
Cohesion: 0.14
Nodes (17): apply_setup_to_state(), _format_display_num(), format_param_display(), impact_frame_display(), render_garage_tweaker(), setup_copy_frame(), _coerce_setup_units(), display_value() (+9 more)

### Community 47 - "Community 47"
Cohesion: 0.09
Nodes (16): _baseline_rows(), collect_evidence(), profile(), generated_setup(), _has_prior(), UnknownTrack, fuel_samples(), plan_fuel() (+8 more)

### Community 48 - "Community 48"
Cohesion: 0.10
Nodes (16): Channel, channel(), inventory(), resolve(), surface_tyre_temp(), wheel_columns(), _wheel_names(), availability() (+8 more)

### Community 49 - "Community 49"
Cohesion: 0.11
Nodes (24): _apply_history(), _change_group(), _enforce_change_budget(), _revert_last_experiment(), _step_of(), LeverStat, SetupHistory, _add_experiment() (+16 more)

### Community 50 - "Community 50"
Cohesion: 0.16
Nodes (28): by_key(), Car, make(), ready_duel(), setup(), test_assignment_by_fingerprint_in_order(), test_balance_from_profiles_reaches_the_ranking(), test_confirm_can_override_the_ranking() (+20 more)

### Community 51 - "Community 51"
Cohesion: 0.11
Nodes (14): render_stint_windows_panel(), per_frame(), deco(), build_lap_summary(), analyze_stint_windows(), build_window_projection(), _detect_stint_segments(), FuelWindow (+6 more)

### Community 52 - "Community 52"
Cohesion: 0.17
Nodes (24): _break_tie(), _clusters(), Contestant, rank_contestants(), _wear_costs(), balance(), laps(), test_a_duel_needs_two_contestants_with_laps() (+16 more)

### Community 53 - "Community 53"
Cohesion: 0.10
Nodes (10): parse_packet(), test_real_capture_every_packet_parses(), test_synthetic_roundtrip_and_rejects(), _lap_packet_recorder(), _sample(), test_frame_shape_and_units(), test_garage_and_stopped_timer_are_not_recorded(), test_integer_channels_are_carried_forward_not_interpolated() (+2 more)

### Community 54 - "Community 54"
Cohesion: 0.07
Nodes (28): CarStatusData, m_actualTyreCompound, m_antiLockBrakes, m_drsActivationDistance, m_drsAllowed, m_enginePowerICE, m_enginePowerMGUK, m_ersDeployedThisLap (+20 more)

### Community 55 - "Community 55"
Cohesion: 0.14
Nodes (14): build_inputs(), delete_tyre_sets(), inventory_payload(), optimise(), OptimiseIn, params_json(), ParamsIn, read_tyre_sets() (+6 more)

### Community 56 - "Community 56"
Cohesion: 0.11
Nodes (15): _derive_helpers(), _derive_speed(), has_telemetry_setup(), _is_missing_setup_value(), load_telemetry(), mean_setup(), _non_reset_rows(), normalize_frame() (+7 more)

### Community 57 - "Community 57"
Cohesion: 0.07
Nodes (29): MotionEXData, m_angularAccelerationX, m_angularAccelerationY, m_angularAccelerationZ, m_angularVelocityX, m_angularVelocityY, m_angularVelocityZ, m_chassisPitch (+21 more)

### Community 58 - "Community 58"
Cohesion: 0.14
Nodes (26): CornerBalance, Lockup, Num, Phase, BalanceStrip(), PHASE_LABEL, Props, BALANCE_SCALE (+18 more)

### Community 59 - "Community 59"
Cohesion: 0.13
Nodes (16): _balance(), by_session_all(), collect_candidates(), _group_text(), _label(), _median_pace(), _num(), run_duel() (+8 more)

### Community 60 - "Community 60"
Cohesion: 0.13
Nodes (15): is_reset_setup(), setup_from_telemetry(), session_by_source(), session_df(), tmp_root(), test_ingest_dataframe_into_empty_library(), test_race_runs_no_longer_include_the_pit_lap(), _build() (+7 more)

### Community 61 - "Community 61"
Cohesion: 0.07
Nodes (25): CarSetupData, m_ballast, m_brakeBias, m_brakePressure, m_engineBraking, m_frontAntiRollBar, m_frontCamber, m_frontLeftTyrePressure (+17 more)

### Community 62 - "Community 62"
Cohesion: 0.12
Nodes (9): best_clean_lap(), build_track_corners(), clean_laps(), ensure_track_corners(), get_track_corners(), NoCleanLap, track_sessions(), catalog_track_names() (+1 more)

### Community 63 - "Community 63"
Cohesion: 0.16
Nodes (20): estimate_setup(), Evidence, snap(), ev(), test_camber_stays_at_meta_whatever_the_evidence(), test_fuel_entry_added_when_given(), test_left_right_mirrored(), test_meta_suspension_package_is_kept() (+12 more)

### Community 64 - "Community 64"
Cohesion: 0.08
Nodes (24): CarDamageData, m_brakesDamage, m_diffuserDamage, m_drsFault, m_engineBlown, m_engineCEWear, m_engineDamage, m_engineESWear (+16 more)

### Community 65 - "Community 65"
Cohesion: 0.14
Nodes (11): app_dir(), bundle_dir(), is_frozen(), default_data_dir(), _backup_db(), repair_library_wheel_axes(), repaired_frame(), _rewrite_parquet() (+3 more)

### Community 66 - "Community 66"
Cohesion: 0.12
Nodes (17): _catalogue_features(), _catalogue_segments(), distance(), _empty(), _entry_speeds(), _estimate(), forward_name(), profile_from_catalogue() (+9 more)

### Community 67 - "Community 67"
Cohesion: 0.16
Nodes (16): detect_corners(), speed_class(), _clean_laps(), _library_sessions(), make_lap(), _real_cases(), test_catalogue_names_follow_the_nearest_apex_and_merge_ranges(), test_complex_without_full_throttle_between_the_minima_is_one_corner() (+8 more)

### Community 68 - "Community 68"
Cohesion: 0.12
Nodes (10): apply_weather_overlay(), character_of(), coherent_suspension(), get_typical_setup(), np_clip(), _pack(), weather_notes(), test_coherent_suspension_only_clamps_to_garage_ranges() (+2 more)

### Community 69 - "Community 69"
Cohesion: 0.08
Nodes (4): PacketLapPositionsData, PacketMotionEXData, PHeader, m_header

### Community 70 - "Community 70"
Cohesion: 0.08
Nodes (14): LapHistoryData, m_lapTimeInMS, m_lapValidBitFlags, m_sector1TimeInMS, m_sector1TimeMinutes, m_sector2TimeInMS, m_sector2TimeMinutes, m_sector3TimeInMS (+6 more)

### Community 71 - "Community 71"
Cohesion: 0.24
Nodes (14): root_of(), _allocation(), AllocationIn, delete_allocation(), delete_overrides(), _overrides(), OverridesIn, read_allocation() (+6 more)

### Community 72 - "Community 72"
Cohesion: 0.09
Nodes (18): CarTelemetryData, m_brake, m_brakesTemperature, m_clutch, m_drs, m_engineRPM, m_engineTemperature, m_gear (+10 more)

### Community 73 - "Community 73"
Cohesion: 0.09
Nodes (20): CarMotionData, m_gForceLateral, m_gForceLongitudinal, m_gForceVertical, m_pitch, m_roll, m_worldForwardDirX, m_worldForwardDirY (+12 more)

### Community 74 - "Community 74"
Cohesion: 0.09
Nodes (20): LiveryColour, blue, green, red, PacketParticipantData, ParticipantData, m_aiControlled, m_driverId (+12 more)

### Community 75 - "Community 75"
Cohesion: 0.20
Nodes (12): _as_state(), is_full_wet(), is_wet_surface(), parse_track_state(), split_conditions(), weather_banner(), session_stint_insights(), session_stint_table() (+4 more)

### Community 76 - "Community 76"
Cohesion: 0.17
Nodes (11): load_session_telemetry(), backfill_progress_from_library(), ensure_progress_schema(), get_track_goal(), pb_history(), _probable_times(), record_session_progress(), scrub_improbable_lap_records() (+3 more)

### Community 77 - "Community 77"
Cohesion: 0.13
Nodes (8): corner_bands(), driver_trace(), pair(), lap_length(), pane(), series(), trace_chart(), _values()

### Community 78 - "Community 78"
Cohesion: 0.10
Nodes (17): EventDataDetails, Buttons, Collision, DriveThroughPenaltyServed, DRSDisabled, FastestLap, Flashback, Overtake (+9 more)

### Community 79 - "Community 79"
Cohesion: 0.24
Nodes (12): BaselineBody, DuelBody, generated_setup(), get_baseline(), name_setup(), NameBody, set_baseline(), _track() (+4 more)

### Community 80 - "Community 80"
Cohesion: 0.25
Nodes (11): _baseline_row(), ensure_duel_schema(), get_baselines(), get_duel(), get_names(), list_duels(), _now(), restore_baseline() (+3 more)

### Community 81 - "Community 81"
Cohesion: 0.10
Nodes (17): FinalClassificationData, m_bestLapTimeInMS, m_gridPosition, m_numLaps, m_numPenalties, m_numPitStops, m_numTyreStints, m_penaltiesTime (+9 more)

### Community 82 - "Community 82"
Cohesion: 0.16
Nodes (10): balance_block(), balance_label(), balance_summary(), _col(), _mean(), _median(), relative_index(), _runs() (+2 more)

### Community 83 - "Community 83"
Cohesion: 0.19
Nodes (17): build(), st, cornerAt(), cssVar(), dot(), draw(), fmt(), hexToRgb() (+9 more)

### Community 84 - "Community 84"
Cohesion: 0.12
Nodes (6): _add_other_track(), full_export_id(), laps(), test_corners_shape_and_delta_bookkeeping(), test_rebuild_error_paths(), test_reference_session_must_be_on_the_same_track()

### Community 85 - "Community 85"
Cohesion: 0.25
Nodes (10): delete_session(), get_session(), health(), library_stats(), list_sessions(), _meta(), patch_session(), _root() (+2 more)

### Community 86 - "Community 86"
Cohesion: 0.21
Nodes (9): track_name(), client(), _has_table(), _laps(), _practice(), test_access_token_rule(), test_duel_start_rank_confirm_stores_duel_and_baseline(), test_stop_keeps_the_duel_without_a_baseline_and_refuses_races() (+1 more)

### Community 87 - "Community 87"
Cohesion: 0.11
Nodes (14): PacketTimeTrialData, TimeTrialDataSet, m_antiLockBrakes, m_carIdx, m_customSetup, m_equalCarPerformance, m_gearboxAssist, m_lapTimeInMS (+6 more)

### Community 88 - "Community 88"
Cohesion: 0.23
Nodes (15): useSession(), useSessions(), LapSummary, SessionMeta, ReferenceChoice, RefMode, useReference(), bestLapNumber() (+7 more)

### Community 89 - "Community 89"
Cohesion: 0.25
Nodes (9): available_wear(), clean_sets(), clear_inventory(), ensure_schema(), get_inventory(), save_inventory(), _track(), test_available_wear_filters_and_sorts() (+1 more)

### Community 90 - "Community 90"
Cohesion: 0.18
Nodes (12): _clean_laps(), laps(), test_channels_default_set(), test_channels_errors(), test_channels_extras_are_wheel_labelled(), test_channels_selection_and_step(), test_compare_extras_return_focus_and_reference(), test_compare_final_delta_matches_lap_time_gap() (+4 more)

### Community 91 - "Community 91"
Cohesion: 0.12
Nodes (16): compilerOptions, isolatedModules, jsx, lib, module, moduleResolution, noFallthroughCasesInSwitch, noUncheckedIndexedAccess (+8 more)

### Community 92 - "Community 92"
Cohesion: 0.20
Nodes (9): _blend(), confidence_level(), _entry(), _evidence_value(), _first_test(), _group_level(), recency_factor(), _transfer() (+1 more)

### Community 94 - "Community 94"
Cohesion: 0.18
Nodes (8): average_profile(), _classes(), corner_table(), _diff(), _group(), _mean(), tag_check(), top_rows()

### Community 95 - "Community 95"
Cohesion: 0.21
Nodes (7): corner_engineer_callouts(), CornerCallout, engineer_sentence(), _f(), format_phase_row(), phase_table_for_display(), render_corner_engineer_panel()

### Community 96 - "Community 96"
Cohesion: 0.13
Nodes (12): LobbyInfoData, m_aiControlled, m_carNumber, m_name, m_nationality, m_platform, m_readyStatus, m_showOnlineNames (+4 more)

### Community 97 - "Community 97"
Cohesion: 0.13
Nodes (11): PacketTyreSetData, TyreSetData, m_actualTyreCompound, m_available, m_fitted, m_lapDeltaTime, m_lifeSpan, m_recommendedSession (+3 more)

### Community 98 - "Community 98"
Cohesion: 0.18
Nodes (7): findPython(), frontendDir, globalSetup(), here, repoRoot, STATE_FILE, waitForHealth()

### Community 99 - "Community 99"
Cohesion: 0.17
Nodes (14): devDependencies, @types/node@22.9.0, @types/react@18.3.12, @types/react-dom@18.3.1, typescript@5.6.3, vitest@2.1.4, name, private (+6 more)

### Community 100 - "Community 100"
Cohesion: 0.22
Nodes (14): applyExternal(), applyZoom(), buildPane(), Built, ChartTheme, drawBands(), drawOverlay(), Props (+6 more)

### Community 101 - "Community 101"
Cohesion: 0.19
Nodes (7): http_port_taken(), load_config(), main(), test_frozen_config_reads_the_toml_next_to_the_exe(), test_frozen_default_library_is_the_exe_folder(), test_load_config(), test_toml_list_is_accepted()

### Community 102 - "Community 102"
Cohesion: 0.30
Nodes (7): BaselineError, _clean_setup(), _duel_setup(), payload(), session_setup(), set_from(), load_session_runs()

### Community 103 - "Community 103"
Cohesion: 0.21
Nodes (9): test_parse_row_garage_tyre_order_and_missing_slash(), test_parse_row_rejects_wrong_shape(), _col_index(), main(), numbers(), parse(), parse_row(), read_sheet() (+1 more)

### Community 104 - "Community 104"
Cohesion: 0.33
Nodes (8): analyze_practice_balance(), _axle_temps(), _efficiency(), _mean_mask(), _phase_masks(), _series(), _steer_norm(), _strength()

### Community 105 - "Community 105"
Cohesion: 0.23
Nodes (6): corner_profile(), frame_coverage(), test_corners_outside_the_frame_are_left_out_and_coverage_is_a_share(), test_times_are_distance_over_speed_and_phases_add_up(), test_without_slip_channels_times_stay_and_balance_is_none(), timed()

### Community 106 - "Community 106"
Cohesion: 0.18
Nodes (13): el(), E(), Dn(), hi(), kt(), i(), Pn(), qn() (+5 more)

### Community 107 - "Community 107"
Cohesion: 0.15
Nodes (13): PacketHeader, m_frameIdentifier, m_gameMajorVersion, m_gameMinorVersion, m_gameYear, m_overallFrameIdentifier, m_packetFormat, m_packetId (+5 more)

### Community 109 - "Community 109"
Cohesion: 0.26
Nodes (10): build(), st, cssVar(), drawBands(), drawOverlay(), fmt(), readTheme(), seriesOpts() (+2 more)

### Community 110 - "Community 110"
Cohesion: 0.24
Nodes (8): _gen(), test_baseline_on_another_track_becomes_evidence(), test_catalogue_only_track_is_prior_only_and_low(), test_make_baseline_round_trip_stores_confidence(), test_own_baseline_is_not_evidence_for_itself_but_generator_still_runs(), test_reverse_layout_uses_forward_layout_evidence(), test_settled_values_are_evidence(), test_target_tracks_own_settled_value_is_absolute()

### Community 111 - "Community 111"
Cohesion: 0.17
Nodes (10): CarTelemetryData2, m_2026Regulations, m_activeAeroActivationDistance, m_activeAeroAvailable, m_activeAeroMode, m_drivingWrongWay, m_overtakeActivationDistance, m_overtakeActive (+2 more)

### Community 112 - "Community 112"
Cohesion: 0.30
Nodes (6): _decimals(), display_text(), garage_display(), test_empty_setup(), test_garage_order_units_and_hidden_keys(), test_text_lists_groups_and_units()

### Community 113 - "Community 113"
Cohesion: 0.18
Nodes (8): @fontsource/titillium-web@5.3.0, react-dom@18.3.1, @tanstack/react-query@5.59.20, queryClient, render(), @fontsource/titillium-web, react-dom, @tanstack/react-query

### Community 114 - "Community 114"
Cohesion: 0.36
Nodes (10): A(), Ae(), D(), oi(), Wt(), Yt(), S(), T() (+2 more)

### Community 116 - "Community 116"
Cohesion: 0.22
Nodes (9): WeatherForecastSample, m_airTemperature, m_airTemperatureChange, m_rainPercentage, m_sessionType, m_timeOffset, m_trackTemperature, m_trackTemperatureChange (+1 more)

### Community 117 - "Community 117"
Cohesion: 0.22
Nodes (4): SessionRow, @playwright/test@1.48.2, PORT, @playwright/test

### Community 118 - "Community 118"
Cohesion: 0.22
Nodes (9): dependencies, @fontsource/jetbrains-mono@5.3.0, react@18.3.1, react-router-dom@6.28.0, uplot@1.6.32, zustand@4.5.5, @fontsource/jetbrains-mono, uplot (+1 more)

### Community 119 - "Community 119"
Cohesion: 0.25
Nodes (9): bn(), En(), Sn(), Tn(), wn(), yn(), zn(), Lt() (+1 more)

### Community 120 - "Community 120"
Cohesion: 0.31
Nodes (3): _small_csv(), test_import_errors(), test_import_upload_and_path()

### Community 122 - "Community 122"
Cohesion: 0.29
Nodes (6): compilerOptions, noEmit, types, extends, include, ../tsconfig.json

### Community 123 - "Community 123"
Cohesion: 0.29
Nodes (7): scripts, build, dev, e2e, preview, test, typecheck

### Community 124 - "Community 124"
Cohesion: 0.33
Nodes (3): _catalogue_spans(), _joined_name(), name_corners()

### Community 125 - "Community 125"
Cohesion: 0.40
Nodes (4): vite@5.4.10, @vitejs/plugin-react@4.3.3, vite, @vitejs/plugin-react

### Community 127 - "Community 127"
Cohesion: 0.50
Nodes (5): bl(), Cl(), Il(), Ol(), Vl()

### Community 129 - "Community 129"
Cohesion: 0.67
Nodes (3): ActiveAeroZone, m_zoneEnd, m_zoneStart

### Community 130 - "Community 130"
Cohesion: 0.67
Nodes (3): DRSZone, m_zoneEnd, m_zoneStart

### Community 131 - "Community 131"
Cohesion: 0.67
Nodes (3): MarshalZone, m_zoneFlag, m_zoneStart

## Knowledge Gaps
- **291 isolated node(s):** `m_frameIdentifier`, `m_gameMajorVersion`, `m_gameMinorVersion`, `m_gameYear`, `m_overallFrameIdentifier` (+286 more)
  These have ≤1 connection - possible missing edges. (Counts symbols only; 1396 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **8 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `normalize_track_name()` connect `Community 40` to `Community 6`, `Community 8`, `Community 11`, `Community 15`, `Community 16`, `Community 21`, `Community 23`, `Community 27`, `Community 30`, `Community 31`, `Community 38`, `Community 42`, `Community 44`, `Community 47`, `Community 55`, `Community 59`, `Community 62`, `Community 66`, `Community 67`, `Community 68`, `Community 71`, `Community 76`, `Community 79`, `Community 85`, `Community 86`, `Community 89`, `Community 92`, `Community 121`?**
  _High betweenness centrality (0.019) - this node is a cross-community bridge._
- **What connects `m_frameIdentifier`, `m_gameMajorVersion`, `m_gameMinorVersion` to the rest of the system?**
  _291 weakly-connected nodes found - possible missing edges._
- **Should `Community 0` be split into smaller, more focused modules?**
  _Cohesion score 0.021739130434782608 - nodes in this community are weakly interconnected._
- **Why does `PHeader` connect `Community 69` to `Community 64`, `Community 32`, `Community 96`, `Community 0`, `Community 97`, `Community 70`, `Community 72`, `Community 73`, `Community 74`, `Community 107`, `Community 78`, `Community 111`, `Community 81`, `Community 93`, `Community 54`, `Community 87`, `Community 61`?**
  _High betweenness centrality (0.019) - this node is a cross-community bridge._
- **Should `Community 1` be split into smaller, more focused modules?**
  _Cohesion score 0.06736741519350214 - nodes in this community are weakly interconnected._
- **Why does `connect()` connect `Community 24` to `Community 7`, `Community 8`, `Community 11`, `Community 14`, `Community 15`, `Community 16`, `Community 35`, `Community 38`, `Community 40`, `Community 44`, `Community 47`, `Community 48`, `Community 49`, `Community 62`, `Community 65`, `Community 76`, `Community 80`, `Community 89`, `Community 110`?**
  _High betweenness centrality (0.016) - this node is a cross-community bridge._
- **Should `Community 2` be split into smaller, more focused modules?**
  _Cohesion score 0.054945054945054944 - nodes in this community are weakly interconnected._