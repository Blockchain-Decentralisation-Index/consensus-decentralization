"""
Generates the clusters file for Solana (clusters/solana.json) from the identifiers file (identifiers/solana.json).
Run from the root directory of the project:
python -m mapping_information.solana_preprocessing.solana_preprocessing
"""
import json
import logging
import os
import pathlib
from collections import Counter

from mapping_information.preprocessing_utils import (
    cluster_by_score,
    compare_homepages,
    normalise_name
)

# ---------------------------------------------------------------------------
# Homepage filtering
# ---------------------------------------------------------------------------

# Solana-specific. Path-style platforms: the operator identity lives in the URL
# *path* (e.g. x.com/<user>, github.com/<user>), so get_domain() collapses every
# user down to the same bare domain and would FALSELY group unrelated validators
# that merely linked the same social/hosting site as their "website". These are
# rejected by filter_homepage so a shared platform domain never counts as a
# homepage signal.
#
# NOTE: subdomain-style hosts (e.g. *.pages.dev, <user>.github.io, *.netlify.app,
# *.vercel.app) are deliberately NOT listed here. There the identity lives in the
# *subdomain*, which get_domain() preserves, so distinct projects get distinct
# domains and a shared subdomain is a GENUINE signal, not a false one.
SHARED_PLATFORM_DOMAINS = {
    'x.com', 'twitter.com', 'github.com', 'keybase.io', 't.me', 'telegram.me',
    'linktr.ee', 'discord.gg', 'discord.com', 'stakewiz.com', 'solanabeach.io',
    'validators.app', 'solscan.io', 'solana.fm'
}


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def score_same_entity(v1, v2):
    """
    Scores how likely two validators belong to the same operator entity.
    Returns a (score, signals) tuple, where signals lists the signal names that
    contributed to the score.

    Solana exposes only two usable signals:
      +3  same valid (non-blacklisted) homepage domain    -> signal 'homepage'
      +2  same normalised name (trailing digits stripped)  -> signal 'name'

    With a threshold of 3, a homepage match alone groups two validators, but a
    name match alone (score 2) never does: it only corroborates a homepage
    match. Unlike Cardano there is NO -1 conflict penalty for different valid
    domains: with only two signals and threshold 3 it would change no outcome,
    so it is omitted for simplicity.
    """
    score = 0
    signals = []

    # Homepage (domain) match, rejecting shared path-style platform domains
    _, same_domain = compare_homepages(
        v1.get('homepage', ''), v2.get('homepage', ''), blocked_domains=SHARED_PLATFORM_DOMAINS
    )
    if same_domain:
        score += 3
        signals.append('homepage')

    # Name match after normalisation
    n1 = normalise_name(v1.get('name', ''))
    n2 = normalise_name(v2.get('name', ''))
    if n1 and n2 and n1 == n2:
        score += 2
        signals.append('name')

    return score, signals


# ---------------------------------------------------------------------------
# Cluster naming
# ---------------------------------------------------------------------------

def determine_cluster_name(validator_names):
    """
    Determines the name of a cluster of validators.

    Solana-specific version of the shared determine_cluster_name in
    preprocessing_utils (used by Cardano). The shared version names a cluster
    after the common prefix of its members' names, which works when members share a brand at the
    start (e.g. "Temporal Topaz"/"Temporal Emerald" -> "Temporal"). On Solana,
    though, members are frequently grouped by a shared HOMEPAGE while their
    names have nothing in common, so a raw common prefix can collapse to a stray
    shared letter (e.g. "SUNREN" + "Solana Vibe Station" -> "S"), which is not a
    real name. We therefore accept the common prefix only when it is a WHOLE
    token (reaches a word boundary). Otherwise we fall back to the full name of
    the alphabetically first member (as the shared version does), so the cluster
    still gets a real, human-meaningful name. Taking only its first word could be
    misleading, e.g. "SUNREN" + "Solana Vibe Station" -> "Solana", which could be
    confused with the chain itself.
    :param validator_names: list of validator names that belong to the same cluster
    :returns: the name of the cluster
    """
    names = [name.title() for name in validator_names if name and name.strip()]
    if not names:
        return ''

    raw_prefix = os.path.commonprefix(names)
    prefix = raw_prefix.strip()

    # The common prefix is usable only if it ends at a word boundary: it was
    # followed by whitespace (which strip() removed), it is exactly one of the
    # member names, or everything after it in every name is just trailing digits
    # (e.g. "Kiln" from "Kiln1"/"Kiln2"). A bare fragment like "S" fails all three.
    prefix_is_whole_token = bool(prefix) and (
        raw_prefix != prefix
        or any(name == prefix for name in names)
        or all(name[len(prefix):].isdigit() for name in names)
    )
    if prefix_is_whole_token:
        return prefix

    # Fallback: full name of the alphabetically first member
    # (de-prioritising names that start with a digit).
    return sorted(names, key=lambda x: (x[0].isdigit(), x))[0]


# ---------------------------------------------------------------------------
# Clustering
# ---------------------------------------------------------------------------

def parse_validator_clusters(validator_data, score_threshold=3):
    """
    Clusters validators by operator entity using homepage/name scoring.

    All validators are included in the output keyed by VOTE ACCOUNT, since
    SolanaMapping.map_from_known_clusters looks up cluster info by the block's
    vote account (its identifier) rather than by the reward (identity) address.
    This differs from Cardano, where the pool hash is both identifier and reward
    address, so keying by vote account applies Cardano's intent (key by the
    stable producer identifier) rather than breaking it.

    Any two validators that score >= score_threshold are placed in the same
    cluster. Transitivity is handled via union-find: if A clusters with B and B
    with C, all three end up in the same cluster. All pairs are compared
    (O(n^2)), which is fine for a one-off preprocessing step over a few hundred
    validators.

    'source' for each validator reflects the signals from the comparison that
    first caused it to be clustered, or ['singleton'] if it was never grouped.
    By construction 'source' can be ['homepage'], ['homepage', 'name'] or
    ['singleton'] — never ['name'] alone, since name (2) < threshold (3).

    :param validator_data: dict keyed by vote account, each value a dict with at
    least 'name' and 'homepage' (the shape of identifiers/solana.json)
    :returns: dict keyed by vote account with 'cluster', 'validator' and 'source'
    """
    logging.info("Parsing validator clusters..")
    return cluster_by_score(
        validator_data, score_same_entity, member_key='validator',
        score_threshold=score_threshold, name_fn=determine_cluster_name
    )


if __name__ == '__main__':
    logging.basicConfig(format='[%(asctime)s] %(message)s', datefmt='%Y/%m/%d %I:%M:%S %p', level=logging.INFO)

    mapping_info_dir = pathlib.Path(__file__).parent.parent

    identifiers_file = mapping_info_dir / 'identifiers' / 'solana.json'
    with open(identifiers_file) as f:
        validator_data = json.load(f)

    clusters = parse_validator_clusters(validator_data)

    clusters_dir = mapping_info_dir / 'clusters'
    clusters_dir.mkdir(exist_ok=True)
    with open(clusters_dir / 'solana.json', 'w') as f:
        json.dump(clusters, f, indent=4)

    # Summary: distribution of 'source' types and multi-member clusters.
    source_dist = Counter(tuple(v['source']) for v in clusters.values())
    cluster_sizes = Counter(v['cluster'] for v in clusters.values())
    multi_member = {name: size for name, size in cluster_sizes.items() if size > 1}
    logging.info(
        f"Done. {len(clusters)} validators | "
        f"source distribution: {dict(source_dist)} | "
        f"{len(multi_member)} multi-member clusters: {multi_member}"
    )
