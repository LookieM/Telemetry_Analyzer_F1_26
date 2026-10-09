"""ingest_dataframe: the shared storage path of CSV import and live recording."""

from __future__ import annotations

import pandas as pd

from telemetry.db import get_session, get_session_laps
from telemetry.import_session import ingest_dataframe
from conftest import needs_library, session_by_source, session_df


@needs_library
def test_ingest_dataframe_into_empty_library(tmp_root):
    session = session_by_source("bahrain_race.csv")
    df = session_df(session)
    kwargs = dict(source_name="live_test", source_hash="a" * 64, original_size=1234, app_root=tmp_root)

    res = ingest_dataframe(df, **kwargs)
    assert not res.already_existed
    assert res.lap_count > 10
    stored = get_session(res.session_id, tmp_root)
    assert stored["source_name"] == "live_test"
    assert stored["session_type"]  # auto-tagged
    assert (tmp_root / stored["telemetry_path"]).exists()
    assert len(get_session_laps(res.session_id, tmp_root)) == res.lap_count

    again = ingest_dataframe(df, **kwargs)
    assert again.already_existed and again.session_id == res.session_id
    assert isinstance(df, pd.DataFrame)
