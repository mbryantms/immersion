from pathlib import Path

from app.ingest.video import find_sidecars, infer_series


def test_infer_series_lfc():
    series, level, ordinal = infer_series(
        "Level 3/Puss in Boots/Puss in Boots 21 Happy Servants/Puss in Boots 21 Happy Servants.mp4"
    )
    assert (series, level, ordinal) == ("Puss in Boots", 3, 21)


def test_infer_series_sxxexx():
    series, level, ordinal = infer_series("Some Show/Some.Show.S02E05.mkv")
    assert series == "Some Show"
    assert ordinal == 205


def test_infer_series_generic_parent_dir():
    series, _level, ordinal = infer_series("My Course/Lesson 07 Introductions.mp4")
    assert series == "My Course"
    assert ordinal == 7


def test_find_sidecars(tmp_path: Path):
    (tmp_path / "Ep 1.mp4").touch()
    (tmp_path / "Ep 1.srt").write_text("x")
    (tmp_path / "Ep 1.en.srt").write_text("x")
    (tmp_path / "Ep 1.zh-Hans.srt").write_text("x")
    (tmp_path / "Ep 12.srt").write_text("x")  # different episode, shares prefix
    (tmp_path / "Ep 1.notes.txt").write_text("x")
    sides = find_sidecars(tmp_path / "Ep 1.mp4")
    by_marker = {s["marker"]: s["lang"] for s in sides}
    assert by_marker[""] is None  # bare .srt -> sniff content
    assert by_marker["en"] == "en"
    assert by_marker["zh-hans"] == "zh"
    # "Ep 12.srt" middle is "2" -> not a language marker -> excluded
    assert len(sides) == 3


def test_episode_position_orders_by_folder(tmp_path: Path):
    from app.ingest.video import episode_position, natural_key

    series = tmp_path / "Level 2" / "Space Patrol"
    dirs = [
        "001 Space Patrol, Mission to Blue Moon 1 The First Day",
        "002 Space Patrol, Mission to Blue Moon 2 A Big Mistake",
        "010 Space Patrol, Mission to Volcano Planet 4 Looking for Birds",
    ]
    for d in dirs:
        (series / d).mkdir(parents=True)
    rel = f"Level 2/{dirs[2]}/whatever.mp4".replace(dirs[2], f"Space Patrol/{dirs[2]}")
    assert episode_position(tmp_path, f"Level 2/Space Patrol/{dirs[0]}/x.mp4") == 1
    assert episode_position(tmp_path, f"Level 2/Space Patrol/{dirs[2]}/x.mp4") == 3
    assert rel  # silence unused warning

    # arcs stay contiguous; internal numbers sort naturally (2 < 10)
    rg = tmp_path / "Level 4" / "Rocket Girl"
    arcs = [
        "Rocket Girl and the Aliens 1 Sloppy Joe Day",
        "Rocket Girl and the Aliens 2 Roxy's Secret",
        "Rocket Girl and the Aliens 10 Finale",
        "Rocket Girl vs. Bubbles 1 Detective Smith",
    ]
    for d in arcs:
        (rg / d).mkdir(parents=True)
    order = sorted(arcs, key=natural_key)
    assert order == [arcs[0], arcs[1], arcs[2], arcs[3]]  # 1, 2, 10, then next arc
    assert episode_position(tmp_path, f"Level 4/Rocket Girl/{arcs[2]}/x.mp4") == 3

    # non-LFC layouts opt out
    assert episode_position(tmp_path, "Somewhere/Show S01E02/x.mp4") is None
