import json
import logging
import os
import pathlib
import re
from collections import Counter, defaultdict
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# Homepage filtering
# ---------------------------------------------------------------------------

# Reused unchanged from cardano_preprocessing.py
INVALID_HOMEPAGES = {
    'https://', 'http://', 'n/a', 'na', '-', '--', '---', '....', '...',
    'tbd', 'coming', 'coming soon', 'in process', 'no webside', 'no website',
    'none', 'null', 'undefined', 'unknown'
}

# Reused unchanged from cardano_preprocessing.py
INVALID_HOMEPAGE_SUBSTRINGS = [
    'foo.com', 'example.com', 'invalidurl', 'test.com',
    'localhost', '127.0.0.1', 'yourdomain', 'yoursite',
    'mysite.com', 'mypool.com', 'poolname.com'
]

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


def get_domain(url):
    """Extracts the domain from a URL, stripping www. (reused from Cardano)"""
    try:
        domain = urlparse(url).netloc.lower()
        return re.sub(r'^www\.', '', domain)
    except Exception:
        return ''


def filter_homepage(homepage):
    """
    Filters out homepages that cannot serve as a genuine operator signal.

    Reused from Cardano, with ONE Solana-specific addition: homepages whose
    domain is a shared path-style platform (SHARED_PLATFORM_DOMAINS) are
    rejected, because those collapse many unrelated validators onto a single
    domain.

    :param homepage: the homepage to be filtered (string)
    :returns: the homepage (as-is) if it is usable, else None
    """
    if not homepage:
        return None

    homepage = homepage.strip()
    if not homepage:
        return None

    homepage_lower = homepage.lower()

    if homepage_lower in INVALID_HOMEPAGES:
        return None

    if any(kw in homepage_lower for kw in INVALID_HOMEPAGE_SUBSTRINGS):
        return None

    # Solana-specific: reject shared path-style platform domains.
    if get_domain(homepage) in SHARED_PLATFORM_DOMAINS:
        return None

    return homepage


# ---------------------------------------------------------------------------
# Name normalisation
# ---------------------------------------------------------------------------

def normalise_name(name):
    """Lowercases, strips trailing digits and whitespace for fuzzy name matching,
    e.g. 'Validator 1' -> 'validator'. (reused from Cardano)"""
    return re.sub(r'\s*\d+$', '', name.strip().lower()).strip()


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

    # Homepage (domain) match
    d1 = get_domain(v1.get('homepage', ''))
    d2 = get_domain(v2.get('homepage', ''))
    filtered_d1 = filter_homepage(v1.get('homepage', ''))
    filtered_d2 = filter_homepage(v2.get('homepage', ''))
    domains_valid = bool(filtered_d1 and filtered_d2 and d1 and d2)
    if domains_valid and d1 == d2:
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

    Adapted from Cardano's version. Cardano names a cluster after the common
    prefix of its members' names, which works when members share a brand at the
    start (e.g. "Temporal Topaz"/"Temporal Emerald" -> "Temporal"). On Solana,
    though, members are frequently grouped by a shared HOMEPAGE while their
    names have nothing in common, so a raw common prefix can collapse to a stray
    shared letter (e.g. "SUNREN" + "Solana Vibe Station" -> "S"), which is not a
    real name. We therefore accept the common prefix only when it is a WHOLE
    token (reaches a word boundary). Otherwise we fall back to the first word of
    the alphabetically first member, so the cluster still gets a real, human-
    meaningful name.
    :param validator_names: list of validator names that belong to the same cluster
    :returns: the name of the cluster
    """
    names = [name.title() for name in validator_names if name]
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

    # Fallback: first word of the alphabetically first member name
    # (de-prioritising names that start with a digit).
    first_name = sorted(names, key=lambda x: (x[0].isdigit(), x))[0]
    tokens = first_name.split()
    return tokens[0] if tokens else prefix


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

    vote_accounts = list(validator_data.keys())
    validators = list(validator_data.values())
    n = len(validators)

    # --- Union-Find (reused from Cardano, unchanged) ---
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]  # path compression
            x = parent[x]
        return x

    def union(x, y):
        parent[find(x)] = find(y)

    # source[i] = signals that caused validator i to be clustered, or None if not yet
    source = [None] * n

    # --- Compare all pairs and merge if above threshold ---
    for i in range(n):
        for j in range(i + 1, n):
            score, signals = score_same_entity(validators[i], validators[j])
            if score >= score_threshold:
                if find(i) != find(j):
                    union(i, j)
                    for idx in [i, j]:
                        if source[idx] is None:
                            source[idx] = signals

    # --- Build clusters ---
    clusters = defaultdict(list)
    for i in range(n):
        clusters[find(i)].append(i)

    # --- Build output ---
    output = {}
    for members in clusters.values():
        validator_names = [validators[i].get('name', '') for i in members]
        cluster_name = determine_cluster_name(validator_names)
        for i in members:
            output[vote_accounts[i]] = {
                'cluster': cluster_name,
                'validator': validators[i].get('name', ''),
                'source': source[i] if source[i] is not None else ['singleton']
            }

    return output


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
