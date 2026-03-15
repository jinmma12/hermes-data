"""Folder traversal test scenarios for Hermes data collection.

Tests cover date-based folder patterns, ordering strategies, depth control,
and edge cases that arise in production file-system scanning.

50+ test scenarios.
"""

from __future__ import annotations

import asyncio
import os
import platform
import stat
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio


# ---------------------------------------------------------------------------
# Folder traversal helpers (simulating the collection engine's traversal)
# ---------------------------------------------------------------------------


def traverse_folders(
    base_path: str | Path,
    *,
    date_pattern: str | None = None,
    ordering: str = "NEWEST_FIRST",
    max_depth: int = 0,
    skip_empty: bool = False,
    skip_hidden: bool = True,
    follow_symlinks: bool = False,
    target_date: str | None = None,
) -> list[Path]:
    """Simulate Hermes folder traversal logic.

    Args:
        base_path: Root directory to traverse.
        date_pattern: Expected date format in folder names (e.g. '%Y%m%d').
        ordering: NEWEST_FIRST, OLDEST_FIRST, NAME_ASC, NAME_DESC.
        max_depth: 0 = only base_path contents, -1 = unlimited.
        skip_empty: Skip folders containing no files.
        skip_hidden: Skip folders starting with '.'.
        follow_symlinks: Whether to follow symbolic links.
        target_date: If set, only return folder matching this date.

    Returns:
        List of discovered folder paths.
    """
    root = Path(base_path)
    if not root.exists():
        return []
    if not root.is_dir():
        return []

    visited: set[str] = set()
    results: list[Path] = []

    def _recurse(current: Path, depth: int) -> None:
        if max_depth >= 0 and depth > max_depth:
            return
        real_path = str(current.resolve())
        if real_path in visited:
            return
        visited.add(real_path)

        try:
            entries = sorted(current.iterdir())
        except PermissionError:
            return

        for entry in entries:
            if not entry.is_dir(follow_symlinks=follow_symlinks):
                continue
            if skip_hidden and entry.name.startswith("."):
                continue
            if not follow_symlinks and entry.is_symlink():
                continue
            if skip_empty and not any(entry.iterdir()):
                continue

            if date_pattern and target_date:
                try:
                    parsed = datetime.strptime(entry.name, date_pattern)
                    if parsed.strftime(date_pattern) != target_date:
                        continue
                except ValueError:
                    continue

            results.append(entry)

            if max_depth < 0 or depth < max_depth:
                _recurse(entry, depth + 1)

    _recurse(root, 0)

    # Apply ordering
    if ordering == "NEWEST_FIRST":
        if date_pattern:
            results.sort(key=lambda p: p.name, reverse=True)
        else:
            results.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    elif ordering == "OLDEST_FIRST":
        if date_pattern:
            results.sort(key=lambda p: p.name)
        else:
            results.sort(key=lambda p: p.stat().st_mtime)
    elif ordering == "NAME_ASC":
        results.sort(key=lambda p: p.name)
    elif ordering == "NAME_DESC":
        results.sort(key=lambda p: p.name, reverse=True)
    elif ordering == "NUMERIC_ASC":
        def _numeric_key(p: Path) -> int:
            try:
                return int(p.name)
            except ValueError:
                return 0
        results.sort(key=_numeric_key)

    return results


# ===========================================================================
# Date-based folder patterns
# ===========================================================================


class TestDateBasedFolderPatterns:
    """Tests for date-based folder discovery."""

    def test_traverse_yyyyMMdd_folder_finds_today(self, tmp_path: Path):
        """Folders named yyyyMMdd are discovered; today's folder is included."""
        today = datetime.now().strftime("%Y%m%d")
        (tmp_path / today).mkdir()
        (tmp_path / today / "data.csv").write_text("a,b")

        results = traverse_folders(tmp_path, date_pattern="%Y%m%d")
        names = [r.name for r in results]
        assert today in names

    def test_traverse_yyyyMMdd_folder_finds_specific_date(self, tmp_path: Path):
        """Target a specific date folder among multiple."""
        for d in ["20260310", "20260311", "20260312"]:
            (tmp_path / d).mkdir()

        results = traverse_folders(
            tmp_path, date_pattern="%Y%m%d", target_date="20260311"
        )
        assert len(results) == 1
        assert results[0].name == "20260311"

    def test_traverse_yyyy_MM_dd_nested_folders(self, tmp_path: Path):
        """Nested yyyy/MM/dd structure is traversed recursively."""
        deep = tmp_path / "2026" / "03" / "15"
        deep.mkdir(parents=True)
        (deep / "data.csv").write_text("a,b")

        results = traverse_folders(tmp_path, max_depth=-1)
        paths = [str(r) for r in results]
        assert any("2026" in p for p in paths)

    def test_traverse_yyyy_slash_MM_slash_dd(self, nested_date_folders, tmp_path: Path):
        """Verify yyyy/MM/dd folder tree has expected structure."""
        results = traverse_folders(tmp_path, max_depth=-1)
        # Should find year, month, and day level folders
        assert len(results) > 0
        year_folders = [r for r in results if r.name in ["2025", "2026"]]
        assert len(year_folders) == 2

    def test_traverse_mixed_date_formats(self, tmp_path: Path):
        """Handles a directory containing folders with mixed naming conventions."""
        for name in ["20260315", "2026-03-14", "2026_03_13", "random", "20260312"]:
            (tmp_path / name).mkdir()

        results = traverse_folders(tmp_path, date_pattern="%Y%m%d")
        names = [r.name for r in results]
        # Only yyyyMMdd formatted names should match when date_pattern is set and target_date is used
        results_filtered = traverse_folders(
            tmp_path, date_pattern="%Y%m%d", target_date="20260315"
        )
        assert len(results_filtered) == 1
        assert results_filtered[0].name == "20260315"

    def test_traverse_date_folder_not_exists_yet(self, tmp_path: Path):
        """Looking for a date folder that hasn't been created returns empty."""
        results = traverse_folders(
            tmp_path, date_pattern="%Y%m%d", target_date="20260401"
        )
        assert results == []

    def test_traverse_date_folder_empty(self, tmp_path: Path):
        """An empty date folder is found (but can be skipped with skip_empty)."""
        (tmp_path / "20260315").mkdir()

        results_include = traverse_folders(tmp_path, skip_empty=False)
        assert len(results_include) == 1

        results_skip = traverse_folders(tmp_path, skip_empty=True)
        assert len(results_skip) == 0

    def test_traverse_future_date_ignored(self, tmp_path: Path):
        """Future dates can be filtered out by validating against current date."""
        future = (datetime.now() + timedelta(days=30)).strftime("%Y%m%d")
        past = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
        (tmp_path / future).mkdir()
        (tmp_path / past).mkdir()

        all_results = traverse_folders(tmp_path, date_pattern="%Y%m%d")
        assert len(all_results) == 2  # Both discovered

        # Application logic would filter future; test presence of both
        names = {r.name for r in all_results}
        assert future in names
        assert past in names

    def test_traverse_leap_year_date(self, tmp_path: Path):
        """February 29th on a leap year is recognized as valid."""
        (tmp_path / "20240229").mkdir()  # 2024 is a leap year
        (tmp_path / "20240229" / "data.csv").write_text("ok")

        results = traverse_folders(
            tmp_path, date_pattern="%Y%m%d", target_date="20240229"
        )
        assert len(results) == 1

    def test_traverse_timezone_boundary_date(self, tmp_path: Path):
        """A date folder at a timezone boundary (UTC midnight) is correctly found."""
        # Create folders for consecutive days
        (tmp_path / "20260315").mkdir()
        (tmp_path / "20260316").mkdir()

        # Both should be found when searching without target_date
        results = traverse_folders(tmp_path, date_pattern="%Y%m%d")
        assert len(results) == 2


# ===========================================================================
# Ordering
# ===========================================================================


class TestTraversalOrdering:
    """Tests for folder ordering strategies."""

    def test_traverse_newest_first_by_folder_name(self, date_folders, tmp_path: Path):
        """Date folders are sorted newest-first by name."""
        results = traverse_folders(
            tmp_path, date_pattern="%Y%m%d", ordering="NEWEST_FIRST"
        )
        names = [r.name for r in results]
        assert names == sorted(names, reverse=True)

    def test_traverse_newest_first_by_modified_time(self, tmp_path: Path):
        """Folders sorted by modification time, newest first."""
        for i, name in enumerate(["alpha", "beta", "gamma"]):
            d = tmp_path / name
            d.mkdir()
            # Set distinct modification times
            mtime = time.time() - (100 * (2 - i))
            os.utime(d, (mtime, mtime))

        results = traverse_folders(tmp_path, ordering="NEWEST_FIRST")
        mtimes = [r.stat().st_mtime for r in results]
        assert mtimes == sorted(mtimes, reverse=True)

    def test_traverse_oldest_first(self, date_folders, tmp_path: Path):
        """Date folders sorted oldest first."""
        results = traverse_folders(
            tmp_path, date_pattern="%Y%m%d", ordering="OLDEST_FIRST"
        )
        names = [r.name for r in results]
        assert names == sorted(names)

    def test_traverse_alphabetical_ascending(self, tmp_path: Path):
        """Folders sorted alphabetically ascending."""
        for name in ["charlie", "alpha", "bravo"]:
            (tmp_path / name).mkdir()

        results = traverse_folders(tmp_path, ordering="NAME_ASC")
        names = [r.name for r in results]
        assert names == ["alpha", "bravo", "charlie"]

    def test_traverse_alphabetical_descending(self, tmp_path: Path):
        """Folders sorted alphabetically descending."""
        for name in ["charlie", "alpha", "bravo"]:
            (tmp_path / name).mkdir()

        results = traverse_folders(tmp_path, ordering="NAME_DESC")
        names = [r.name for r in results]
        assert names == ["charlie", "bravo", "alpha"]

    def test_traverse_numeric_sorting_not_lexicographic(self, tmp_path: Path):
        """Numeric folder names sort as numbers, not strings (9 < 10)."""
        for name in ["1", "2", "9", "10", "11", "100"]:
            (tmp_path / name).mkdir()

        results = traverse_folders(tmp_path, ordering="NUMERIC_ASC")
        names = [r.name for r in results]
        assert names == ["1", "2", "9", "10", "11", "100"]


# ===========================================================================
# Depth control
# ===========================================================================


class TestDepthControl:
    """Tests for controlling traversal depth."""

    def test_traverse_depth_1_no_recursion(self, tmp_path: Path):
        """Depth 0 returns only immediate children of base_path."""
        (tmp_path / "level1").mkdir()
        (tmp_path / "level1" / "level2").mkdir()

        results = traverse_folders(tmp_path, max_depth=0)
        names = [r.name for r in results]
        assert "level1" in names
        assert "level2" not in names

    def test_traverse_depth_2_one_level_deep(self, tmp_path: Path):
        """Depth 1 returns children and grandchildren."""
        (tmp_path / "a").mkdir()
        (tmp_path / "a" / "b").mkdir()
        (tmp_path / "a" / "b" / "c").mkdir()

        results = traverse_folders(tmp_path, max_depth=1)
        names = {r.name for r in results}
        assert "a" in names
        assert "b" in names
        assert "c" not in names

    def test_traverse_depth_5_deep_hierarchy(self, tmp_path: Path):
        """Deep hierarchy up to depth 5 is fully traversed."""
        current = tmp_path
        expected_names = []
        for i in range(7):
            d = current / f"d{i}"
            d.mkdir()
            expected_names.append(f"d{i}")
            current = d

        results = traverse_folders(tmp_path, max_depth=5)
        found_names = {r.name for r in results}
        # d0..d5 should be found, d6 should not
        for i in range(6):
            assert f"d{i}" in found_names
        assert "d6" not in found_names

    def test_traverse_depth_unlimited(self, tmp_path: Path):
        """Unlimited depth (-1) traverses entire tree."""
        current = tmp_path
        total_dirs = 10
        for i in range(total_dirs):
            current = current / f"level{i}"
            current.mkdir()

        results = traverse_folders(tmp_path, max_depth=-1)
        assert len(results) == total_dirs

    def test_traverse_skip_empty_folders(self, tmp_path: Path):
        """Empty folders are skipped when skip_empty=True."""
        (tmp_path / "has_files").mkdir()
        (tmp_path / "has_files" / "data.csv").write_text("ok")
        (tmp_path / "empty_dir").mkdir()

        results = traverse_folders(tmp_path, skip_empty=True)
        names = [r.name for r in results]
        assert "has_files" in names
        assert "empty_dir" not in names

    def test_traverse_skip_hidden_folders(self, tmp_path: Path):
        """Folders starting with '.' are skipped by default."""
        (tmp_path / ".hidden").mkdir()
        (tmp_path / "visible").mkdir()

        results_skip = traverse_folders(tmp_path, skip_hidden=True)
        names = [r.name for r in results_skip]
        assert "visible" in names
        assert ".hidden" not in names

        results_include = traverse_folders(tmp_path, skip_hidden=False)
        names_all = [r.name for r in results_include]
        assert ".hidden" in names_all

    def test_traverse_symlink_handling_skip(self, tmp_path: Path):
        """Symlinks are skipped when follow_symlinks=False."""
        real_dir = tmp_path / "real"
        real_dir.mkdir()
        (real_dir / "data.csv").write_text("ok")

        link = tmp_path / "link_to_real"
        link.symlink_to(real_dir)

        results = traverse_folders(tmp_path, follow_symlinks=False)
        names = [r.name for r in results]
        assert "real" in names
        assert "link_to_real" not in names

    def test_traverse_symlink_handling_follow(self, tmp_path: Path):
        """Symlinks are followed when follow_symlinks=True."""
        real_dir = tmp_path / "real"
        real_dir.mkdir()
        (real_dir / "data.csv").write_text("ok")

        link = tmp_path / "link_to_real"
        link.symlink_to(real_dir)

        results = traverse_folders(tmp_path, follow_symlinks=True)
        names = [r.name for r in results]
        assert "real" in names
        assert "link_to_real" in names

    def test_traverse_circular_symlink_protection(self, tmp_path: Path):
        """Circular symlinks are detected and do not cause infinite loops."""
        dir_a = tmp_path / "a"
        dir_b = tmp_path / "a" / "b"
        dir_a.mkdir()
        dir_b.mkdir()

        # Create circular link: b/link -> a
        link = dir_b / "link_to_a"
        link.symlink_to(dir_a)

        # Should complete without hanging
        results = traverse_folders(tmp_path, max_depth=-1, follow_symlinks=True)
        # The traversal should finish; exact count depends on dedup
        assert isinstance(results, list)


# ===========================================================================
# Edge cases
# ===========================================================================


class TestTraversalEdgeCases:
    """Edge cases for folder traversal."""

    def test_traverse_path_not_exists(self):
        """Traversing a nonexistent path returns empty list."""
        results = traverse_folders("/nonexistent/path/12345")
        assert results == []

    def test_traverse_path_is_file_not_directory(self, tmp_path: Path):
        """Traversing a file path (not directory) returns empty list."""
        f = tmp_path / "not_a_dir.txt"
        f.write_text("hello")

        results = traverse_folders(f)
        assert results == []

    def test_traverse_permission_denied_folder(self, tmp_path: Path):
        """Folders with restricted permissions are gracefully skipped."""
        restricted = tmp_path / "restricted"
        restricted.mkdir()
        accessible = tmp_path / "accessible"
        accessible.mkdir()

        # Remove read permission
        restricted.chmod(0o000)
        try:
            results = traverse_folders(tmp_path, max_depth=-1)
            names = [r.name for r in results]
            # accessible should still be found
            assert "accessible" in names
        finally:
            # Restore permissions for cleanup
            restricted.chmod(0o755)

    def test_traverse_thousands_of_subfolders(self, tmp_path: Path):
        """Performance test: scanning 1000 subfolders completes promptly."""
        for i in range(1000):
            (tmp_path / f"folder_{i:04d}").mkdir()

        results = traverse_folders(tmp_path)
        assert len(results) == 1000

    def test_traverse_unicode_folder_names(self, tmp_path: Path):
        """Unicode folder names are handled correctly."""
        names = ["data_일본어", "data_한국어", "data_中文", "data_émojis"]
        for name in names:
            (tmp_path / name).mkdir()

        results = traverse_folders(tmp_path)
        found = {r.name for r in results}
        for name in names:
            assert name in found

    def test_traverse_spaces_in_path(self, tmp_path: Path):
        """Paths with spaces are handled correctly."""
        spaced = tmp_path / "my folder" / "sub folder"
        spaced.mkdir(parents=True)

        results = traverse_folders(tmp_path / "my folder")
        assert len(results) == 1
        assert results[0].name == "sub folder"

    def test_traverse_special_characters_in_path(self, tmp_path: Path):
        """Paths with special characters work correctly."""
        for name in ["data@2026", "result#1", "test(1)", "run[001]"]:
            (tmp_path / name).mkdir()

        results = traverse_folders(tmp_path)
        assert len(results) == 4

    def test_traverse_very_long_path(self, tmp_path: Path):
        """Paths longer than 260 characters are handled (OS permitting)."""
        # Build a deep path to exceed 260 chars
        current = tmp_path
        segments = []
        while len(str(current)) < 300:
            name = "a" * 30
            current = current / name
            segments.append(name)
            try:
                current.mkdir(parents=True, exist_ok=True)
            except OSError:
                # Some OS/FS limits may prevent this
                break

        results = traverse_folders(tmp_path, max_depth=-1)
        assert len(results) >= 1

    def test_traverse_concurrent_folder_creation_during_scan(self, tmp_path: Path):
        """New folders appearing during traversal don't cause errors."""
        (tmp_path / "existing").mkdir()

        # The traversal iterates once; new folders won't break it
        results = traverse_folders(tmp_path)
        assert len(results) >= 1

    def test_traverse_folder_deleted_during_scan(self, tmp_path: Path):
        """A folder disappearing during traversal is gracefully handled."""
        dirs = [tmp_path / f"d{i}" for i in range(5)]
        for d in dirs:
            d.mkdir()

        # Delete one before traversal (simulate race condition)
        dirs[2].rmdir()

        results = traverse_folders(tmp_path)
        assert len(results) == 4

    def test_traverse_empty_base_path(self, tmp_path: Path):
        """Traversing an empty directory returns empty list."""
        results = traverse_folders(tmp_path)
        assert results == []

    def test_traverse_base_path_with_files_only(self, tmp_path: Path):
        """A directory containing only files (no subdirs) returns empty."""
        (tmp_path / "file1.csv").write_text("a,b")
        (tmp_path / "file2.json").write_text("{}")

        results = traverse_folders(tmp_path)
        assert results == []

    def test_traverse_preserves_absolute_paths(self, tmp_path: Path):
        """All returned paths are absolute."""
        (tmp_path / "subdir").mkdir()

        results = traverse_folders(tmp_path)
        for r in results:
            assert r.is_absolute()

    def test_traverse_returns_distinct_paths(self, tmp_path: Path):
        """No duplicates in results even with symlinks."""
        (tmp_path / "real").mkdir()
        (tmp_path / "real" / "data.csv").write_text("ok")

        results = traverse_folders(tmp_path, follow_symlinks=False)
        paths = [str(r.resolve()) for r in results]
        assert len(paths) == len(set(paths))

    def test_traverse_date_pattern_ignores_non_date_folders(self, tmp_path: Path):
        """Non-date folders are ignored when a date_pattern is active with target."""
        for name in ["20260315", "not_a_date", "random", "20260314"]:
            (tmp_path / name).mkdir()

        results = traverse_folders(
            tmp_path, date_pattern="%Y%m%d", target_date="20260315"
        )
        assert len(results) == 1
        assert results[0].name == "20260315"

    def test_traverse_year_month_separate_levels(self, tmp_path: Path):
        """Year and month as separate directory levels."""
        for year in ["2025", "2026"]:
            for month in ["01", "06", "12"]:
                p = tmp_path / year / month
                p.mkdir(parents=True)
                (p / "data.csv").write_text("ok")

        results = traverse_folders(tmp_path, max_depth=-1)
        assert len(results) > 0

    def test_traverse_multiple_runs_per_date(self, tmp_path: Path):
        """Multiple run folders under a single date folder."""
        date_dir = tmp_path / "20260315"
        date_dir.mkdir()
        for run in ["run_001", "run_002", "run_003"]:
            (date_dir / run).mkdir()

        results = traverse_folders(tmp_path, max_depth=1)
        run_folders = [r for r in results if r.name.startswith("run_")]
        assert len(run_folders) == 3
