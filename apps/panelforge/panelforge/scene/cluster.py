"""Grouping appearances into identities, and backgrounds into locations.

Pure numpy, no models: the inputs are feature vectors and distance matrices
that other modules produce. Distances are normalised so that 1.0 is the
"same thing" threshold for every feature kind, which lets the CCIP embedding
and the colour histograms be blended without retuning either.
"""

from __future__ import annotations

from typing import Sequence

import numpy as np

INF = 1e9


def chi2_matrix(hists: np.ndarray) -> np.ndarray:
    """Symmetric chi-square distance between rows of L1-normalised histograms."""
    h = np.asarray(hists, dtype=np.float64)
    if len(h) == 0:
        return np.zeros((0, 0))
    a = h[:, None, :]
    b = h[None, :, :]
    s = a + b
    with np.errstate(divide="ignore", invalid="ignore"):
        d = np.where(s > 0, (a - b) ** 2 / s, 0.0)
    return 0.5 * d.sum(axis=2)


def cosine_matrix(vectors: np.ndarray) -> np.ndarray:
    v = np.asarray(vectors, dtype=np.float64)
    if len(v) == 0:
        return np.zeros((0, 0))
    n = v / np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-12)
    return 1.0 - n @ n.T


def blend(
    parts: Sequence[tuple[np.ndarray, float, float]],
) -> np.ndarray:
    """Weighted mean of distance matrices, each divided by its own threshold.

    parts = [(matrix, threshold, weight)]. A NaN in a matrix means "this pair
    has no such feature" and that part is skipped for that pair only.
    """
    total = None
    weights = None
    for m, thr, w in parts:
        m = np.asarray(m, dtype=np.float64) / thr
        have = ~np.isnan(m)
        m = np.where(have, m, 0.0)
        total = m * w if total is None else total + m * w
        weights = have * w if weights is None else weights + have * w
    if total is None or weights is None:
        return np.zeros((0, 0))
    with np.errstate(invalid="ignore", divide="ignore"):
        out = np.where(weights > 0, total / np.maximum(weights, 1e-12), INF)
    np.fill_diagonal(out, 0.0)
    return out


def average_linkage(
    dist: np.ndarray,
    threshold: float = 1.0,
    cannot_link: Sequence[Sequence[int]] = (),
) -> list[int]:
    """Agglomerative clustering with average linkage.

    Merges the closest pair of clusters while their mean pairwise distance is
    below `threshold`. `cannot_link` lists groups of indices that must end in
    different clusters (two people drawn in the same panel are two people).
    Returns a label per item, labels numbered 0.. in order of first item.
    """
    d = np.asarray(dist, dtype=np.float64)
    n = len(d)
    if n == 0:
        return []
    clusters: dict[int, list[int]] = {i: [i] for i in range(n)}
    group_of: dict[int, set[int]] = {i: set() for i in range(n)}
    for g, members in enumerate(cannot_link):
        for i in members:
            group_of[i].add(g)
    groups = {i: set(group_of[i]) for i in range(n)}
    # sums[i][j] = sum of pairwise distances between clusters i and j
    sums = d.copy()
    sizes = {i: 1 for i in range(n)}
    active = set(range(n))

    while len(active) > 1:
        best = None
        best_d = threshold
        act = sorted(active)
        for ai, i in enumerate(act):
            for j in act[ai + 1 :]:
                if groups[i] & groups[j]:
                    continue
                mean = sums[i, j] / (sizes[i] * sizes[j])
                if mean < best_d:
                    best_d = mean
                    best = (i, j)
        if best is None:
            break
        i, j = best
        clusters[i].extend(clusters.pop(j))
        groups[i] |= groups.pop(j)
        sums[i, :] += sums[j, :]
        sums[:, i] += sums[:, j]
        sizes[i] += sizes.pop(j)
        active.discard(j)

    labels = [0] * n
    ordered = sorted(clusters.values(), key=min)
    for label, members in enumerate(ordered):
        for i in members:
            labels[i] = label
    return labels


def quantile_linkage(
    dist: np.ndarray,
    threshold: float = 1.0,
    cannot_link: Sequence[Sequence[int]] = (),
    q: float = 0.25,
) -> list[int]:
    """Agglomerative clustering that merges on a low quantile, not the mean.

    Average linkage asks every pair of pictures of a character to look alike,
    so one person drawn from the front, in profile and in shadow splits into
    three "characters". Taking the q-quantile of the cross distances instead
    asks only that a good share of the pairs match, which is what actually
    happens in a comic, while still being far stricter than single linkage
    (one lucky pair). `cannot_link` groups still end in different clusters.
    """
    d = np.asarray(dist, dtype=np.float64)
    n = len(d)
    if n == 0:
        return []
    members: dict[int, list[int]] = {i: [i] for i in range(n)}
    groups: dict[int, set[int]] = {i: set() for i in range(n)}
    for g, group in enumerate(cannot_link):
        for i in group:
            groups[i].add(g)
    # A score matrix between clusters, kept up to date: after a merge only
    # the merged cluster's row and column are re-scored. The old version
    # re-scored every pair on every merge, which on ten chapters (1400
    # appearances) took minutes; this is the same merges in the same order.
    score = d.copy()
    np.fill_diagonal(score, np.inf)
    for i in range(n):
        for j in range(i + 1, n):
            if groups[i] & groups[j]:
                score[i, j] = score[j, i] = np.inf
    active = np.ones(n, dtype=bool)
    while active.sum() > 1:
        sub = score[np.ix_(active, active)]
        flat = int(np.argmin(sub))
        best_d = float(sub.flat[flat])
        if not best_d < threshold:
            break
        idx = np.flatnonzero(active)
        a, b = int(idx[flat // len(idx)]), int(idx[flat % len(idx)])
        i, j = (a, b) if a < b else (b, a)
        members[i].extend(members.pop(j))
        groups[i] |= groups.pop(j)
        active[j] = False
        score[j, :] = np.inf
        score[:, j] = np.inf
        for m in np.flatnonzero(active):
            m = int(m)
            if m == i:
                continue
            if groups[i] & groups[m]:
                val = np.inf
            else:
                val = float(np.quantile(d[np.ix_(members[i], members[m])], q))
            score[i, m] = score[m, i] = val
    labels = [0] * n
    for label, group_members in enumerate(sorted(members.values(), key=min)):
        for i in group_members:
            labels[i] = label
    return labels


def recurring(
    labels: Sequence[int],
    panel_ids: Sequence[str],
    scene_ids: Sequence[str],
    min_panels: int = 3,
    min_scenes: int = 2,
) -> set[int]:
    """Clusters that count as cast rather than one-off extras.

    Cast: seen in at least `min_panels` panels, or in two panels that belong to
    at least `min_scenes` different scenes.
    """
    panels: dict[int, set[str]] = {}
    scenes: dict[int, set[str]] = {}
    for label, pid, sid in zip(labels, panel_ids, scene_ids):
        panels.setdefault(label, set()).add(pid)
        scenes.setdefault(label, set()).add(sid)
    return {
        label
        for label in panels
        if len(panels[label]) >= min_panels
        or (len(panels[label]) >= 2 and len(scenes[label]) >= min_scenes)
    }


def nearest_centroid(
    dist_to_centroids: np.ndarray, threshold: float = 1.0
) -> list[int | None]:
    """For each row, the column index of the closest centroid under threshold."""
    d = np.asarray(dist_to_centroids, dtype=np.float64)
    out: list[int | None] = []
    for row in d:
        if row.size == 0:
            out.append(None)
            continue
        j = int(np.argmin(row))
        out.append(j if row[j] < threshold else None)
    return out


def purity(labels: Sequence[int], truth: Sequence[str]) -> float:
    """Share of items whose cluster's majority truth label matches their own."""
    by: dict[int, dict[str, int]] = {}
    for label, t in zip(labels, truth):
        by.setdefault(label, {}).setdefault(t, 0)
        by[label][t] += 1
    if not labels:
        return 1.0
    return sum(max(c.values()) for c in by.values()) / len(labels)
