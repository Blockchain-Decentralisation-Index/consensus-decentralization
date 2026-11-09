"""
Shared helpers for the ledger-specific preprocessing scripts (e.g. cardano_preprocessing, solana_preprocessing)
that generate the identifiers and clusters files under mapping_information/.
"""
import os
import re
from collections import defaultdict
from urllib.parse import urlparse


INVALID_HOMEPAGES = {
    'https://', 'http://', 'n/a', 'na', '-', '--', '---', '....', '...',
    'tbd', 'coming', 'coming soon', 'in process', 'no webside', 'no website',
    'none', 'null', 'undefined', 'unknown'
}

INVALID_HOMEPAGE_SUBSTRINGS = [
    'foo.com', 'example.com', 'invalidurl', 'test.com',
    'localhost', '127.0.0.1', 'yourdomain', 'yoursite',
    'mysite.com', 'mypool.com', 'poolname.com'
]


def get_domain(url):
    """Extracts the domain from a URL, stripping www."""
    try:
        domain = urlparse(url).netloc.lower()
        return re.sub(r'^www\.', '', domain)
    except Exception:
        return ''


def filter_homepage(homepage, blocked_domains=frozenset()):
    """
    Filters out homepages that cannot serve as a genuine operator signal. Specifically, it ignores homepage entries
    that are empty, have an 'empty' name (e.g. 'n/a'), include a dummy keyword in their name (e.g. foo.com) or whose
    domain is in blocked_domains.
    :param homepage: the homepage to be filtered (string)
    :param blocked_domains: optional collection of domains to reject, e.g. shared path-style platforms (x.com,
    github.com) where the operator identity lives in the URL path, so all operators collapse onto the same domain
    :returns: the homepage (as it is) if it is usable, else None
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

    if blocked_domains and get_domain(homepage) in blocked_domains:
        return None

    return homepage


def compare_homepages(homepage1, homepage2, blocked_domains=frozenset()):
    """
    Compares the domains of two homepages.
    :param homepage1: the first homepage (string)
    :param homepage2: the second homepage (string)
    :param blocked_domains: optional collection of domains to reject (see filter_homepage)
    :returns: tuple (domains_valid, same_domain), where domains_valid is True if both homepages pass filter_homepage
    and have a non-empty domain, and same_domain is True if additionally both domains are equal
    """
    d1 = get_domain(homepage1)
    d2 = get_domain(homepage2)
    domains_valid = bool(
        filter_homepage(homepage1, blocked_domains) and filter_homepage(homepage2, blocked_domains) and d1 and d2
    )
    return domains_valid, domains_valid and d1 == d2


def normalise_name(name):
    """Lowercases, strips trailing digits and whitespace for fuzzy name matching,
    e.g. 'Ray Network 1' -> 'ray network'."""
    return re.sub(r'\s*\d+$', '', name.strip().lower()).strip()


def determine_cluster_name(names):
    """
    Determines the name of a cluster.
    First, it checks if there is a common prefix among all names. If there is, it uses that as the cluster name.
    If no common prefix exists, then it names the cluster after the first name (in alphabetical order and
    prioritizing names that don't start with a digit)
    :param names: list of names (e.g. pool names) that belong to the same cluster
    :returns: the name of the cluster
    """
    # make sure names have consistent case and filter out empty names
    names = [name.title() for name in names if name]
    if not names:
        return ''
    common_prefix = os.path.commonprefix(names)
    if common_prefix:
        common_prefix = common_prefix.strip()
        return common_prefix
    # if there is no common prefix, sort names alphabetically, prioritizing names that don't start with a digit
    # and use the first one as the cluster name
    names = sorted(names, key=lambda x: (x[0].isdigit(), x))
    return names[0]


def cluster_by_score(entries, score_fn, member_key, score_threshold=3, name_fn=determine_cluster_name):
    """
    Clusters entries (e.g. pools or validators) by operator entity using a pairwise scoring function.

    Any two entries that score >= score_threshold are placed in the same cluster.
    Transitivity is handled via union-find: if A clusters with B and B with C,
    all three end up in the same cluster.

    All pairs of entries are compared, which means that the complexity is O(n^2)
    but should be fine since it only runs once as a preprocessing step.

    Source for each entry reflects the signals from the comparison that first
    caused it to be clustered, or ['singleton'] if it was never grouped.
    :param entries: dictionary, where each key is an entry's id (the key of the output file) and the corresponding
    value is a dictionary with the entry's metadata (including at least 'name')
    :param score_fn: function that takes two metadata dictionaries and returns a (score, signals) tuple
    :param member_key: the field under which each entry's own name is stored in the output (e.g. 'pool')
    :param score_threshold: the minimum score for two entries to be placed in the same cluster
    :param name_fn: function that takes a list of names and returns the name of the cluster
    :returns: dictionary keyed by entry id, with 'cluster', member_key and 'source' for each entry
    """
    ids = list(entries.keys())
    items = list(entries.values())
    n = len(items)

    # --- Union-Find ---
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]  # path compression
            x = parent[x]
        return x

    def union(x, y):
        parent[find(x)] = find(y)

    # source[i] = signals that caused entry i to be clustered, or None if not yet
    source = [None] * n

    # --- Compare all pairs and merge if above threshold ---
    for i in range(n):
        for j in range(i + 1, n):
            score, signals = score_fn(items[i], items[j])
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
        names = [items[i].get('name', '') for i in members]
        cluster_name = name_fn(names)
        for i in members:
            output[ids[i]] = {
                'cluster': cluster_name,
                member_key: items[i].get('name', ''),
                'source': source[i] if source[i] is not None else ['singleton']
            }

    return output