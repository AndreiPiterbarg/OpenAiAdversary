import json

import pytest

from domains.swe_agents.scripts.interactive_astra_batch import aggregate, shard_registration


def manifest():
    tasks = [{"key": str(i)} for i in range(3)]
    return {"tasks": tasks, "runs": [
        {"id": f"task-{i}-cell-{c}-rep-{r}", "task": task, "cell_index": c,
         "repetition": r, "cell": {"a": "off", "b": "off"}, "seed": 5000 + r}
        for r in range(5) for i, task in enumerate(tasks) for c in range(4)]}


def test_twelve_shards_exactly_partition_sixty_runs():
    value = manifest()
    shards = [shard_registration(value, i, c) for i in range(3) for c in range(4)]
    ids = [r["id"] for s in shards for r in s["runs"]]
    assert len(ids) == len(set(ids)) == 60
    assert set(ids) == {r["id"] for r in value["runs"]}
    assert len({s["canonical_manifest_sha256"] for s in shards}) == 1
    for i, c in [(-1, 0), (3, 0), (0, 4), (True, 0)]:
        with pytest.raises(ValueError):
            shard_registration(value, i, c)


def test_aggregation_keeps_missing_sixty_denominator_and_refuses_foreign_shard(tmp_path):
    value = manifest()
    shard = shard_registration(value, 0, 0)
    (tmp_path / "registration.json").write_text(json.dumps(shard))
    result = aggregate(value, [tmp_path])
    assert result["planned"] == result["unknown"] == 60
    shard["canonical_manifest_sha256"] = "bad"
    (tmp_path / "registration.json").write_text(json.dumps(shard))
    with pytest.raises(ValueError, match="canonical"):
        aggregate(value, [tmp_path])


def test_discovery_shards_preserve_twenty_run_denominator(tmp_path):
    value = manifest()
    value["tasks"] = value["tasks"][:1]
    value["runs"] = [row for row in value["runs"] if row["task"]["key"] == "0"]
    value["kind"] = "astra_twenty_episode_discovery_batch"
    shards = [shard_registration(value, 0, cell) for cell in range(4)]
    assert len({row["id"] for shard in shards for row in shard["runs"]}) == 20
    with pytest.raises(ValueError, match="invalid shard"):
        shard_registration(value, 1, 0)
    result = aggregate(value, [])
    assert result["planned"] == result["unknown"] == 20
    assert result["kind"] == "astra_twenty_episode_discovery_batch"
