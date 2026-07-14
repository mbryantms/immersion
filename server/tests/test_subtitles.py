from pathlib import Path

from app.ingest.align_tracks import assign_en, dedupe_consecutive
from app.ingest.subtitles import (
    Cue,
    cjk_ratio,
    parse_cues,
    segment_cues,
    sniff_read,
)


def test_parse_malformed_srt(fixtures: Path):
    cues, enc = parse_cues(fixtures / "malformed.srt", "zh")
    texts = [c.text for c in cues]
    assert "这是第一句。" in texts
    assert "带标签的一句。" in texts  # tags stripped
    assert "最后一句。" in texts  # multi-line zh joined without separator
    assert all(c.text for c in cues)  # empty cue dropped
    assert enc.startswith("utf-8")


def test_gb18030_detection(tmp_path: Path):
    p = tmp_path / "gbk.srt"
    p.write_bytes("1\n00:00:01,000 --> 00:00:02,000\n这是国标编码的字幕。\n".encode("gb18030"))
    text, enc = sniff_read(p)
    assert "国标编码" in text
    assert enc == "gb18030"


def test_cjk_ratio_sniffs_language():
    assert cjk_ratio("这是中文字幕内容啊") > 0.8
    assert cjk_ratio("This is English text only") < 0.05


def test_segment_merges_incomplete_cues():
    cues = [
        Cue(0, 1000, "这是一个很长的"),
        Cue(1100, 2000, "句子。"),  # gap 100ms, previous incomplete -> merge
        Cue(2100, 3000, "独立的句子。"),
    ]
    segs = segment_cues(cues)
    assert [s.text for s in segs] == ["这是一个很长的句子。", "独立的句子。"]
    assert (segs[0].t0_ms, segs[0].t1_ms) == (0, 2000)


def test_segment_gap_flushes_incomplete():
    cues = [Cue(0, 1000, "没有标点的"), Cue(2000, 3000, "下一句。")]
    segs = segment_cues(cues)  # 1000ms gap > 500ms threshold
    assert [s.text for s in segs] == ["没有标点的", "下一句。"]


def test_segment_runaway_guard():
    cues = [Cue(i * 1000, i * 1000 + 900, f"词{i}") for i in range(10)]  # never any punct
    segs = segment_cues(cues)
    assert all(len(s.text) <= 4 * 2 + 4 for s in segs)  # flushed at MERGE_MAX_CUES
    assert len(segs) >= 2


def test_segment_keeps_quote_closers():
    cues = [Cue(0, 1000, "他说：“你好。”"), Cue(1100, 2000, "然后走了。")]
    segs = segment_cues(cues)
    assert len(segs) == 2  # 。” counts as sentence-final


def test_dedupe_consecutive_en_paragraphs():
    # the verified LFC pattern: one paragraph copied across consecutive cues
    cues = [
        Cue(0, 1000, "Same paragraph."),
        Cue(1000, 2000, "Same paragraph."),
        Cue(2000, 3000, "Same paragraph."),
        Cue(3000, 4000, "Different."),
    ]
    out = dedupe_consecutive(cues)
    assert len(out) == 2
    assert out[0].t0_ms == 0 and out[0].t1_ms == 3000


def test_assign_en_overlap():
    from app.ingest.subtitles import Segment

    segs = [Segment(0, 2000, "第一句。"), Segment(2000, 4000, "第二句。"), Segment(9000, 9500, "无英文。")]
    en = [Cue(0, 1900, "First."), Cue(1950, 4100, "Second."), Cue(5000, 6000, "Orphan.")]
    out = assign_en(segs, en)
    assert out[0][0] == "First."
    assert out[1][0] == "Second."
    assert out[2] == (None, 0.0)
    assert out[0][1] > 0.9


def test_assign_en_many_to_one():
    from app.ingest.subtitles import Segment

    # one long zh sentence spanning two short en cues -> both joined
    segs = [Segment(0, 4000, "很长的一句话。")]
    en = [Cue(0, 2000, "First half,"), Cue(2000, 4000, "second half.")]
    out = assign_en(segs, en)
    assert out[0][0] == "First half, second half."
