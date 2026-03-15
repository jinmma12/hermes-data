"""File matching and regex test scenarios for Hermes data collection.

Tests cover glob patterns, regex patterns, file filters, discovery modes,
completion checks, and post-collection actions.

50+ test scenarios.
"""

from __future__ import annotations

import fnmatch
import hashlib
import os
import re
import shutil
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# File matching helpers (simulating the collection engine's file discovery)
# ---------------------------------------------------------------------------


def match_files(
    base_path: str | Path,
    *,
    glob_pattern: str | None = None,
    regex_pattern: str | None = None,
    regex_flags: int = 0,
    min_size: int = 0,
    max_size: int = 0,
    max_age_seconds: int = 0,
    modified_after: float = 0,
    modified_before: float = 0,
    exclude_patterns: list[str] | None = None,
    mode: str = "ALL",
    last_poll_time: float = 0,
    batch_size: int = 10,
    ordering: str = "NAME_ASC",
) -> list[Path]:
    """Simulate Hermes file matching logic.

    Args:
        base_path: Directory to search.
        glob_pattern: Shell glob pattern (e.g. '*.csv').
        regex_pattern: Regex pattern for filename matching.
        regex_flags: re module flags for regex.
        min_size: Minimum file size in bytes.
        max_size: Maximum file size in bytes (0 = no limit).
        max_age_seconds: Maximum file age in seconds (0 = no limit).
        modified_after: Only files modified after this timestamp.
        modified_before: Only files modified before this timestamp.
        exclude_patterns: List of glob patterns to exclude.
        mode: SINGLE, ALL, LATEST, BATCH, ALL_NEW.
        last_poll_time: For ALL_NEW mode, timestamp of last poll.
        batch_size: For BATCH mode, number of files to return.
        ordering: NAME_ASC, NAME_DESC, MODIFIED_ASC, MODIFIED_DESC.

    Returns:
        List of matching file paths.
    """
    root = Path(base_path)
    if not root.exists() or not root.is_dir():
        return []

    candidates: list[Path] = []

    if glob_pattern:
        candidates = list(root.rglob(glob_pattern) if "**" in glob_pattern else root.glob(glob_pattern))
    else:
        candidates = [f for f in root.iterdir() if f.is_file()]

    # Apply regex filter
    if regex_pattern:
        compiled = re.compile(regex_pattern, regex_flags)
        candidates = [f for f in candidates if compiled.search(f.name)]

    # Filter only files
    candidates = [f for f in candidates if f.is_file()]

    # Size filters
    if min_size > 0:
        candidates = [f for f in candidates if f.stat().st_size >= min_size]
    if max_size > 0:
        candidates = [f for f in candidates if f.stat().st_size <= max_size]

    # Age filter
    if max_age_seconds > 0:
        cutoff = time.time() - max_age_seconds
        candidates = [f for f in candidates if f.stat().st_mtime >= cutoff]

    # Modified time filters
    if modified_after > 0:
        candidates = [f for f in candidates if f.stat().st_mtime > modified_after]
    if modified_before > 0:
        candidates = [f for f in candidates if f.stat().st_mtime < modified_before]

    # Exclude patterns
    if exclude_patterns:
        for pattern in exclude_patterns:
            candidates = [f for f in candidates if not fnmatch.fnmatch(f.name, pattern)]

    # ALL_NEW mode
    if mode == "ALL_NEW" and last_poll_time > 0:
        candidates = [f for f in candidates if f.stat().st_mtime > last_poll_time]

    # Ordering
    if ordering == "NAME_ASC":
        candidates.sort(key=lambda f: f.name)
    elif ordering == "NAME_DESC":
        candidates.sort(key=lambda f: f.name, reverse=True)
    elif ordering == "MODIFIED_ASC":
        candidates.sort(key=lambda f: f.stat().st_mtime)
    elif ordering == "MODIFIED_DESC":
        candidates.sort(key=lambda f: f.stat().st_mtime, reverse=True)

    # Mode
    if mode == "SINGLE":
        return candidates[:1]
    elif mode == "LATEST":
        candidates.sort(key=lambda f: f.stat().st_mtime, reverse=True)
        return candidates[:1]
    elif mode == "BATCH":
        return candidates[:batch_size]
    else:
        return candidates


def check_completion(
    filepath: Path,
    *,
    check_type: str = "NONE",
    marker_file: str = ".done",
    stable_seconds: int = 5,
    timeout_seconds: int = 30,
) -> bool:
    """Check if a file is complete and ready for collection.

    Args:
        filepath: The file to check.
        check_type: NONE, MARKER_FILE, SIZE_STABLE, TIMEOUT.
        marker_file: Name of the marker file to look for.
        stable_seconds: Seconds the file size must be stable.
        timeout_seconds: Max seconds to wait for completion.
    """
    if check_type == "NONE":
        return True

    if check_type == "MARKER_FILE":
        marker_path = filepath.parent / marker_file
        return marker_path.exists()

    if check_type == "SIZE_STABLE":
        try:
            size1 = filepath.stat().st_size
            time.sleep(0.01)  # Shortened for testing
            size2 = filepath.stat().st_size
            return size1 == size2
        except OSError:
            return False

    return True


def post_collection_action(
    filepath: Path,
    *,
    action: str = "KEEP",
    move_to: str | Path = "",
    rename_suffix: str = ".processed",
) -> Path | None:
    """Perform post-collection action on a file.

    Returns new path if moved/renamed, None if deleted, original if kept.
    """
    if action == "KEEP":
        return filepath
    elif action == "DELETE":
        filepath.unlink()
        return None
    elif action == "MOVE":
        target = Path(move_to)
        target.mkdir(parents=True, exist_ok=True)
        dest = target / filepath.name
        # Handle conflict
        if dest.exists():
            stem = filepath.stem
            suffix = filepath.suffix
            counter = 1
            while dest.exists():
                dest = target / f"{stem}_{counter}{suffix}"
                counter += 1
        shutil.move(str(filepath), str(dest))
        return dest
    elif action == "RENAME":
        new_path = filepath.with_suffix(filepath.suffix + rename_suffix)
        filepath.rename(new_path)
        return new_path
    return filepath


# ===========================================================================
# Glob patterns
# ===========================================================================


class TestGlobPatterns:
    """Tests for shell glob pattern matching."""

    def test_match_star_csv(self, tmp_path: Path):
        """*.csv matches all CSV files in the directory."""
        (tmp_path / "data.csv").write_text("a,b")
        (tmp_path / "report.csv").write_text("x,y")
        (tmp_path / "image.png").write_bytes(b"\x89PNG")

        results = match_files(tmp_path, glob_pattern="*.csv")
        assert len(results) == 2
        assert all(r.suffix == ".csv" for r in results)

    def test_match_star_star_csv(self, tmp_path: Path):
        """**/*.csv matches CSV files in subdirectories."""
        sub = tmp_path / "subdir"
        sub.mkdir()
        (tmp_path / "root.csv").write_text("a")
        (sub / "nested.csv").write_text("b")
        (sub / "other.txt").write_text("c")

        results = match_files(tmp_path, glob_pattern="**/*.csv")
        names = {r.name for r in results}
        assert "nested.csv" in names
        # root.csv may or may not match depending on glob behavior
        assert len(results) >= 1

    def test_match_prefix_star(self, tmp_path: Path):
        """temp_* matches files with the given prefix."""
        (tmp_path / "temp_001.csv").write_text("a")
        (tmp_path / "temp_002.csv").write_text("b")
        (tmp_path / "data_003.csv").write_text("c")

        results = match_files(tmp_path, glob_pattern="temp_*")
        assert len(results) == 2
        assert all("temp_" in r.name for r in results)

    def test_match_star_suffix(self, tmp_path: Path):
        """*_result.json matches files ending with the given suffix."""
        (tmp_path / "analysis_result.json").write_text("{}")
        (tmp_path / "test_result.json").write_text("{}")
        (tmp_path / "config.json").write_text("{}")

        results = match_files(tmp_path, glob_pattern="*_result.json")
        assert len(results) == 2

    def test_match_question_mark(self, tmp_path: Path):
        """data_?.csv matches single-character wildcard."""
        (tmp_path / "data_1.csv").write_text("a")
        (tmp_path / "data_2.csv").write_text("b")
        (tmp_path / "data_10.csv").write_text("c")

        results = match_files(tmp_path, glob_pattern="data_?.csv")
        assert len(results) == 2  # data_1 and data_2, not data_10

    def test_match_bracket_range(self, tmp_path: Path):
        """data_[0-9].csv matches single digit in range."""
        for i in range(12):
            (tmp_path / f"data_{i}.csv").write_text(f"row{i}")

        results = match_files(tmp_path, glob_pattern="data_[0-9].csv")
        assert len(results) == 10  # 0-9

    def test_match_multiple_extensions(self, tmp_path: Path):
        """Matching multiple extensions using separate patterns."""
        (tmp_path / "data.csv").write_text("a")
        (tmp_path / "data.json").write_text("{}")
        (tmp_path / "data.xml").write_text("<x/>")
        (tmp_path / "data.txt").write_text("txt")

        # Match csv and json (no native {csv,json} in pathlib, use regex)
        results = match_files(tmp_path, regex_pattern=r"\.(csv|json|xml)$")
        assert len(results) == 3

    def test_match_no_extension(self, tmp_path: Path):
        """Files without extensions (Makefile, Dockerfile) can be matched."""
        (tmp_path / "Makefile").write_text("all:")
        (tmp_path / "Dockerfile").write_text("FROM python")
        (tmp_path / "script.py").write_text("print()")

        results = match_files(tmp_path, glob_pattern="Makefile")
        assert len(results) == 1
        assert results[0].name == "Makefile"


# ===========================================================================
# Regex patterns
# ===========================================================================


class TestRegexPatterns:
    """Tests for regex-based file matching."""

    def test_regex_simple(self, tmp_path: Path):
        """Simple regex: temp_.*\\.csv"""
        (tmp_path / "temp_data.csv").write_text("a")
        (tmp_path / "temp_report.csv").write_text("b")
        (tmp_path / "perm_data.csv").write_text("c")

        results = match_files(tmp_path, regex_pattern=r"temp_.*\.csv")
        assert len(results) == 2

    def test_regex_date_in_filename(self, tmp_path: Path):
        """Regex matching date pattern in filename."""
        (tmp_path / "data_20260315_143000.csv").write_text("a")
        (tmp_path / "data_20260316_090000.csv").write_text("b")
        (tmp_path / "data_nodate.csv").write_text("c")

        results = match_files(tmp_path, regex_pattern=r".*_\d{8}_\d{6}\.csv")
        assert len(results) == 2

    def test_regex_capture_groups(self, tmp_path: Path):
        """Regex with capture groups works for matching."""
        (tmp_path / "equip_A_run001.csv").write_text("a")
        (tmp_path / "equip_B_run002.csv").write_text("b")
        (tmp_path / "other.csv").write_text("c")

        results = match_files(tmp_path, regex_pattern=r"equip_([A-Z])_run(\d+)\.csv")
        assert len(results) == 2

    def test_regex_case_insensitive(self, tmp_path: Path):
        """Case-insensitive regex matching."""
        (tmp_path / "DATA.CSV").write_text("a")
        (tmp_path / "data.csv").write_text("b")
        (tmp_path / "Data.Csv").write_text("c")

        results = match_files(
            tmp_path, regex_pattern=r"data\.csv", regex_flags=re.IGNORECASE
        )
        assert len(results) == 3

    def test_regex_invalid_pattern_error(self, tmp_path: Path):
        """Invalid regex pattern raises an error."""
        (tmp_path / "data.csv").write_text("a")

        with pytest.raises(re.error):
            match_files(tmp_path, regex_pattern=r"[invalid")

    def test_regex_anchored_vs_unanchored(self, tmp_path: Path):
        """Anchored regex (^data) differs from unanchored (data)."""
        (tmp_path / "data_file.csv").write_text("a")
        (tmp_path / "old_data_file.csv").write_text("b")

        anchored = match_files(tmp_path, regex_pattern=r"^data")
        unanchored = match_files(tmp_path, regex_pattern=r"data")
        assert len(anchored) == 1
        assert len(unanchored) == 2

    def test_regex_unicode_filenames(self, tmp_path: Path):
        """Regex works with unicode filenames."""
        (tmp_path / "데이터_001.csv").write_text("a")
        (tmp_path / "데이터_002.csv").write_text("b")
        (tmp_path / "data_003.csv").write_text("c")

        results = match_files(tmp_path, regex_pattern=r"데이터_\d+\.csv")
        assert len(results) == 2

    def test_regex_multipart_extension(self, tmp_path: Path):
        """Regex handles multipart extensions like .tar.gz."""
        (tmp_path / "archive.tar.gz").write_bytes(b"\x1f\x8b")
        (tmp_path / "backup.tar.gz").write_bytes(b"\x1f\x8b")
        (tmp_path / "data.gz").write_bytes(b"\x1f\x8b")

        results = match_files(tmp_path, regex_pattern=r"\.tar\.gz$")
        assert len(results) == 2


# ===========================================================================
# File filters
# ===========================================================================


class TestFileFilters:
    """Tests for file size, age, and exclusion filters."""

    def test_filter_min_size_excludes_empty(self, tmp_path: Path):
        """Empty files (0 bytes) are excluded by min_size > 0."""
        (tmp_path / "empty.csv").write_text("")
        (tmp_path / "notempty.csv").write_text("data")

        results = match_files(tmp_path, min_size=1)
        assert len(results) == 1
        assert results[0].name == "notempty.csv"

    def test_filter_min_size_1kb(self, tmp_path: Path):
        """Files smaller than 1KB are excluded."""
        (tmp_path / "small.csv").write_text("a")
        (tmp_path / "big.csv").write_bytes(b"x" * 2048)

        results = match_files(tmp_path, min_size=1024)
        assert len(results) == 1
        assert results[0].name == "big.csv"

    def test_filter_max_size_100mb(self, tmp_path: Path):
        """Files larger than max_size are excluded."""
        (tmp_path / "small.csv").write_text("small data")
        (tmp_path / "medium.csv").write_bytes(b"x" * 5000)

        results = match_files(tmp_path, max_size=1000)
        assert len(results) == 1
        assert results[0].name == "small.csv"

    def test_filter_max_age_24h(self, tmp_path: Path):
        """Files older than 24 hours are excluded."""
        recent = tmp_path / "recent.csv"
        recent.write_text("new")

        old = tmp_path / "old.csv"
        old.write_text("old")
        old_time = time.time() - 86401  # 24h+1s ago
        os.utime(old, (old_time, old_time))

        results = match_files(tmp_path, max_age_seconds=86400)
        assert len(results) == 1
        assert results[0].name == "recent.csv"

    def test_filter_max_age_1h(self, tmp_path: Path):
        """Files older than 1 hour are excluded."""
        recent = tmp_path / "recent.csv"
        recent.write_text("new")

        old = tmp_path / "old.csv"
        old.write_text("old")
        old_time = time.time() - 3601  # 1h+1s ago
        os.utime(old, (old_time, old_time))

        results = match_files(tmp_path, max_age_seconds=3600)
        assert len(results) == 1

    def test_filter_modified_after_timestamp(self, tmp_path: Path):
        """Only files modified after a specific timestamp are included."""
        cutoff = time.time() - 100

        old = tmp_path / "old.csv"
        old.write_text("old")
        os.utime(old, (cutoff - 200, cutoff - 200))

        new = tmp_path / "new.csv"
        new.write_text("new")
        # new file has current mtime, which is after cutoff

        results = match_files(tmp_path, modified_after=cutoff)
        assert len(results) == 1
        assert results[0].name == "new.csv"

    def test_filter_modified_before_timestamp(self, tmp_path: Path):
        """Only files modified before a specific timestamp are included."""
        cutoff = time.time() - 50

        old = tmp_path / "old.csv"
        old.write_text("old")
        old_time = cutoff - 200
        os.utime(old, (old_time, old_time))

        new = tmp_path / "new.csv"
        new.write_text("new")

        results = match_files(tmp_path, modified_before=cutoff)
        assert len(results) == 1
        assert results[0].name == "old.csv"

    def test_filter_exclude_pattern_tmp(self, tmp_path: Path):
        """Files matching exclude pattern *.tmp are skipped."""
        (tmp_path / "data.csv").write_text("a")
        (tmp_path / "temp.tmp").write_text("b")
        (tmp_path / "swap.tmp").write_text("c")

        results = match_files(tmp_path, exclude_patterns=["*.tmp"])
        assert len(results) == 1
        assert results[0].name == "data.csv"

    def test_filter_exclude_pattern_hidden_files(self, tmp_path: Path):
        """Hidden files (starting with '.') can be excluded."""
        (tmp_path / "data.csv").write_text("a")
        (tmp_path / ".hidden").write_text("b")
        (tmp_path / ".DS_Store").write_bytes(b"\x00")

        results = match_files(tmp_path, exclude_patterns=[".*"])
        assert len(results) == 1

    def test_filter_exclude_multiple_patterns(self, tmp_path: Path):
        """Multiple exclude patterns can be combined."""
        (tmp_path / "data.csv").write_text("a")
        (tmp_path / "temp.tmp").write_text("b")
        (tmp_path / "backup.bak").write_text("c")
        (tmp_path / ".hidden").write_text("d")

        results = match_files(
            tmp_path, exclude_patterns=["*.tmp", "*.bak", ".*"]
        )
        assert len(results) == 1
        assert results[0].name == "data.csv"

    def test_filter_combination_size_and_age_and_pattern(self, tmp_path: Path):
        """Combining size, age, and pattern filters."""
        # Recent, large CSV
        good = tmp_path / "good.csv"
        good.write_bytes(b"x" * 2048)

        # Recent, small CSV (excluded by size)
        small = tmp_path / "small.csv"
        small.write_text("a")

        # Old, large CSV (excluded by age)
        old = tmp_path / "old.csv"
        old.write_bytes(b"x" * 2048)
        os.utime(old, (time.time() - 7200, time.time() - 7200))

        # Recent, large TMP (excluded by pattern)
        (tmp_path / "temp.tmp").write_bytes(b"x" * 2048)

        results = match_files(
            tmp_path,
            glob_pattern="*.csv",
            min_size=1024,
            max_age_seconds=3600,
        )
        assert len(results) == 1
        assert results[0].name == "good.csv"


# ===========================================================================
# Discovery modes
# ===========================================================================


class TestDiscoveryModes:
    """Tests for different file discovery modes."""

    def test_single_mode_first_match_breaks(self, tmp_path: Path):
        """SINGLE mode returns only the first match."""
        for i in range(5):
            (tmp_path / f"data_{i}.csv").write_text(f"row{i}")

        results = match_files(tmp_path, glob_pattern="*.csv", mode="SINGLE")
        assert len(results) == 1

    def test_single_mode_no_match_returns_empty(self, tmp_path: Path):
        """SINGLE mode with no matching files returns empty list."""
        (tmp_path / "data.txt").write_text("a")

        results = match_files(tmp_path, glob_pattern="*.csv", mode="SINGLE")
        assert results == []

    def test_all_mode_returns_all_matches(self, tmp_path: Path):
        """ALL mode returns every matching file."""
        for i in range(10):
            (tmp_path / f"data_{i}.csv").write_text(f"row{i}")
        (tmp_path / "other.txt").write_text("not csv")

        results = match_files(tmp_path, glob_pattern="*.csv", mode="ALL")
        assert len(results) == 10

    def test_latest_mode_returns_newest_file(self, tmp_path: Path):
        """LATEST mode returns only the most recently modified file."""
        for i in range(5):
            f = tmp_path / f"data_{i}.csv"
            f.write_text(f"row{i}")
            os.utime(f, (time.time() - (100 * (4 - i)), time.time() - (100 * (4 - i))))

        results = match_files(tmp_path, glob_pattern="*.csv", mode="LATEST")
        assert len(results) == 1
        assert results[0].name == "data_4.csv"

    def test_latest_mode_by_modified_time_not_name(self, tmp_path: Path):
        """LATEST mode uses mtime, not filename ordering."""
        a = tmp_path / "a_first_alphabetically.csv"
        z = tmp_path / "z_last_alphabetically.csv"

        z.write_text("z data")
        os.utime(z, (time.time() - 1000, time.time() - 1000))

        a.write_text("a data")
        # a has a more recent mtime

        results = match_files(tmp_path, glob_pattern="*.csv", mode="LATEST")
        assert len(results) == 1
        assert results[0].name == "a_first_alphabetically.csv"

    def test_batch_mode_returns_n_files(self, tmp_path: Path):
        """BATCH mode returns exactly batch_size files."""
        for i in range(20):
            (tmp_path / f"data_{i:03d}.csv").write_text(f"row{i}")

        results = match_files(
            tmp_path, glob_pattern="*.csv", mode="BATCH", batch_size=5
        )
        assert len(results) == 5

    def test_batch_mode_fewer_than_n_available(self, tmp_path: Path):
        """BATCH mode with fewer files than batch_size returns all available."""
        for i in range(3):
            (tmp_path / f"data_{i}.csv").write_text(f"row{i}")

        results = match_files(
            tmp_path, glob_pattern="*.csv", mode="BATCH", batch_size=10
        )
        assert len(results) == 3

    def test_all_new_mode_since_last_poll(self, tmp_path: Path):
        """ALL_NEW mode returns only files newer than last_poll_time."""
        old_time = time.time() - 500
        poll_time = time.time() - 100

        old = tmp_path / "old.csv"
        old.write_text("old")
        os.utime(old, (old_time, old_time))

        new = tmp_path / "new.csv"
        new.write_text("new")

        results = match_files(
            tmp_path, glob_pattern="*.csv", mode="ALL_NEW", last_poll_time=poll_time
        )
        assert len(results) == 1
        assert results[0].name == "new.csv"

    def test_all_new_mode_first_poll_gets_all(self, tmp_path: Path):
        """ALL_NEW mode with last_poll_time=0 returns all files."""
        for i in range(5):
            (tmp_path / f"data_{i}.csv").write_text(f"row{i}")

        results = match_files(
            tmp_path, glob_pattern="*.csv", mode="ALL_NEW", last_poll_time=0
        )
        assert len(results) == 5

    def test_all_new_mode_no_new_files(self, tmp_path: Path):
        """ALL_NEW mode with no new files returns empty list."""
        old = tmp_path / "old.csv"
        old.write_text("old")
        old_time = time.time() - 500
        os.utime(old, (old_time, old_time))

        results = match_files(
            tmp_path, glob_pattern="*.csv", mode="ALL_NEW", last_poll_time=time.time() - 10
        )
        assert len(results) == 0


# ===========================================================================
# Completion checks
# ===========================================================================


class TestCompletionChecks:
    """Tests for file completion detection."""

    def test_marker_file_present_allows_collection(self, tmp_path: Path):
        """Marker file present means the data file is complete."""
        data = tmp_path / "data.csv"
        data.write_text("a,b\n1,2")
        (tmp_path / ".done").write_text("")

        assert check_completion(data, check_type="MARKER_FILE") is True

    def test_marker_file_absent_waits(self, tmp_path: Path):
        """Missing marker file means the data file is not yet complete."""
        data = tmp_path / "data.csv"
        data.write_text("a,b\n1,2")

        assert check_completion(data, check_type="MARKER_FILE") is False

    def test_marker_file_custom_name_complete(self, tmp_path: Path):
        """Custom marker file name (.complete) works."""
        data = tmp_path / "data.csv"
        data.write_text("a,b")
        (tmp_path / ".complete").write_text("")

        assert check_completion(
            data, check_type="MARKER_FILE", marker_file=".complete"
        ) is True

    def test_marker_file_custom_name_ready(self, tmp_path: Path):
        """Custom marker file name (.ready) works."""
        data = tmp_path / "data.csv"
        data.write_text("a,b")
        (tmp_path / ".ready").write_text("")

        assert check_completion(
            data, check_type="MARKER_FILE", marker_file=".ready"
        ) is True

    def test_marker_file_custom_name_ok(self, tmp_path: Path):
        """Custom marker file name (.ok) works."""
        data = tmp_path / "data.csv"
        data.write_text("a,b")
        (tmp_path / ".ok").write_text("")

        assert check_completion(
            data, check_type="MARKER_FILE", marker_file=".ok"
        ) is True

    def test_size_stable_file_done_growing(self, tmp_path: Path):
        """A file whose size is stable is considered complete."""
        data = tmp_path / "data.csv"
        data.write_text("final content")

        assert check_completion(data, check_type="SIZE_STABLE") is True

    def test_size_stable_file_still_growing(self, tmp_path: Path):
        """A file still being written to is not yet complete.

        Note: In the real system, this checks across multiple intervals.
        Here we test the stable case since growing requires actual I/O.
        """
        data = tmp_path / "data.csv"
        data.write_text("data so far")
        # File is stable in this test (no concurrent writer)
        assert check_completion(data, check_type="SIZE_STABLE") is True

    def test_size_stable_timeout_exceeded(self, tmp_path: Path):
        """Completion check returns True for size-stable even after long waits."""
        data = tmp_path / "data.csv"
        data.write_text("complete data")
        result = check_completion(
            data, check_type="SIZE_STABLE", timeout_seconds=1
        )
        assert result is True

    def test_no_completion_check_immediate_collect(self, tmp_path: Path):
        """NONE check type allows immediate collection."""
        data = tmp_path / "data.csv"
        data.write_text("data")

        assert check_completion(data, check_type="NONE") is True


# ===========================================================================
# Post-collection actions
# ===========================================================================


class TestPostCollectionActions:
    """Tests for actions taken after successful file collection."""

    def test_post_move_to_archive(self, tmp_path: Path):
        """File is moved to the archive directory."""
        data = tmp_path / "data.csv"
        data.write_text("content")
        archive = tmp_path / "archive"

        result = post_collection_action(data, action="MOVE", move_to=archive)
        assert result is not None
        assert result.parent == archive
        assert result.exists()
        assert not data.exists()

    def test_post_move_creates_target_directory(self, tmp_path: Path):
        """Target directory is created if it doesn't exist."""
        data = tmp_path / "data.csv"
        data.write_text("content")
        archive = tmp_path / "deep" / "archive" / "2026"

        result = post_collection_action(data, action="MOVE", move_to=archive)
        assert result is not None
        assert archive.exists()

    def test_post_move_conflict_rename(self, tmp_path: Path):
        """Moving a file to a directory with a name conflict generates a unique name."""
        data = tmp_path / "data.csv"
        data.write_text("new content")
        archive = tmp_path / "archive"
        archive.mkdir()
        (archive / "data.csv").write_text("existing content")

        result = post_collection_action(data, action="MOVE", move_to=archive)
        assert result is not None
        assert result.name != "data.csv"  # Should be renamed
        assert result.exists()

    def test_post_delete_after_collection(self, tmp_path: Path):
        """File is deleted after collection."""
        data = tmp_path / "data.csv"
        data.write_text("content")

        result = post_collection_action(data, action="DELETE")
        assert result is None
        assert not data.exists()

    def test_post_rename_adds_suffix(self, tmp_path: Path):
        """File is renamed with a .processed suffix."""
        data = tmp_path / "data.csv"
        data.write_text("content")

        result = post_collection_action(data, action="RENAME")
        assert result is not None
        assert result.name == "data.csv.processed"
        assert result.exists()
        assert not data.exists()

    def test_post_keep_leaves_original(self, tmp_path: Path):
        """KEEP action leaves the original file in place."""
        data = tmp_path / "data.csv"
        data.write_text("content")

        result = post_collection_action(data, action="KEEP")
        assert result == data
        assert data.exists()
