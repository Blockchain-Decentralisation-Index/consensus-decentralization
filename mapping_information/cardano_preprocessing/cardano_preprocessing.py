"""
Generates the identifiers and clusters files for Cardano from pool metadata.
Run from the root directory of the project:
python -m mapping_information.cardano_preprocessing.cardano_preprocessing
"""
import pathlib
import google.cloud.bigquery as bq
import json
import argparse
import logging
import re

from mapping_information.preprocessing_utils import (
    cluster_by_score,
    compare_homepages,
    filter_homepage,
    get_domain,
    normalise_name
)


def get_pool_data_BQ(force_query):
    """
    Queries the BigQuery database for pool data and writes it to a json file.
    :param force_query: flag to specify whether to query for project data regardless if the relevant data already exist.
    :returns: dictionary, where each key is a pool's hash and the corresponding value is a dictionary with the
    pool's metadata (name, ticker, homepage, description)
    """
    logging.info("Getting pool data..")
    filename = 'cardano_pool_data_BQ.json'
    file = pathlib.Path(mapping_info_dir / "cardano_preprocessing" / filename)
    if not force_query and file.is_file():
        # logging.info('Pool data already exists locally. '
        #              'For querying anyway please run the script using the flag --force-query')
        with open(file) as f:
            pool_data = json.load(f)
        return pool_data

    client = bq.Client.from_service_account_json(json_credentials_path=mapping_info_dir / "google-service-account-key.json")

    query = ('SELECT pool_hash, json as metadata FROM `iog-data-analytics.cardano_mainnet.pool_offline_data`')
    logging.info("Fetching pool data from BigQuery..")
    query_job = client.query(query)
    try:
        rows = query_job.result()
    except Exception as e:
        logging.info(f'The following exception was raised: {repr(e)}')
        return None
    pool_data = {row[0]: json.loads(row[1]) for row in rows}
    # write json to file
    with open(file, 'w') as f:
        json.dump(pool_data, f, indent=4)
    logging.info('Pool data saved locally.')
    return pool_data


def get_pool_data_node():
    """
    Gets pool data that has been fetched from a Cardano node.
    :returns: dictionary, where each key is a pool's hash and the corresponding value is a dictionary with the
    pool's metadata (name, ticker, homepage, description)
    """
    filename = 'cardano_pool_data_node.json'
    file = pathlib.Path(mapping_info_dir / "cardano_preprocessing" / filename)
    with open(file) as f:
        pool_data = json.load(f)
    return pool_data


def merge_pool_data(pool_data_BQ, pool_data_node):
    """
    Merges pool data from BigQuery and from a Cardano node, giving priority to node data in case of conflicts.
    :param pool_data_BQ: dictionary with pool data that was fetched from BigQuery
    :param pool_data_node: dictionary with pool data that was fetched from a Cardano node
    :returns: dictionary, where each key is a pool's hash and the corresponding value is a dictionary with the
    pool's metadata (name, ticker, homepage, description).
    """
    logging.info("Merging pool data sources..")
    if pool_data_BQ is None:
        return pool_data_node
    if pool_data_node is None:
        return pool_data_BQ
    merged = pool_data_BQ | pool_data_node
    return merged


def parse_pool_identifiers(pool_data):
    """
    Extracts identifier information from pool data .
    Specifically, for each unique identifier (ticker) it saves the corresponding pool name and homepage and writes
    all of them to a json file.
    Conflicting tickers (same ticker, different domains) are flagged and
    excluded from identifiers to avoid false mapping.
    :param pool_data: dictionary, where each key is a pool's hash and the corresponding value is a dictionary with the
    pool's metadata (name, ticker, homepage, description)
    """
    logging.info("Parsing pool identifiers..")

    identifiers = dict()
    conflicts = dict()

    for pool in pool_data.values():
        ticker = pool.get('ticker', '').strip().upper()
        name = pool.get('name', '').strip()
        homepage = pool.get('homepage', '').strip()

        if not ticker:
            continue

        if ticker not in identifiers:
            identifiers[ticker] = {'name': name, 'link': homepage}
        else:
            existing = identifiers[ticker]
            same_domain = (
                get_domain(existing['link']) == get_domain(homepage)
                and bool(filter_homepage(homepage))
            )
            if not same_domain:
                # Genuine conflict — flag it
                if ticker not in conflicts:
                    conflicts[ticker] = [{'name': existing['name'], 'link': existing['link']}]
                conflicts[ticker].append({'name': name, 'link': homepage})

    # Remove conflicting tickers from identifiers to avoid false mapping
    for ticker in conflicts:
        identifiers.pop(ticker, None)

    return identifiers, conflicts


def normalise_ticker(ticker):
    """Strips trailing digits from a ticker for fuzzy matching, e.g. RAY1 -> RAY.
    If the ticker is entirely numeric, it's left unchanged."""
    stripped = re.sub(r'\d+$', '', ticker.strip().upper())
    return stripped if stripped else ticker.strip().upper()


def score_same_entity(p1, p2):
    """
    Scores how likely two pools belong to the same operator entity.
    Returns a (score, signals) tuple where signals is a list of the signal
    names that contributed positively to the score (excluding penalties).

    Scoring:
      +3  same non-trivial domain
      +2  same ticker (after stripping trailing digits)
      +2  same name (after stripping trailing digits)
      +1  same (non-empty) description
      -1  different non-trivial domains (conflict signal)
    """
    score = 0
    signals = []

    # Domain match
    domains_valid, same_domain = compare_homepages(p1.get('homepage', ''), p2.get('homepage', ''))
    if same_domain:
        score += 3
        signals.append('homepage')
    elif domains_valid:
        score -= 1

    # Ticker match after normalisation (i.e. removing trailing digits, which often indicate different pools of the same operator)
    t1 = normalise_ticker(p1.get('ticker', ''))
    t2 = normalise_ticker(p2.get('ticker', ''))
    if bool(t1 and t2 and t1 == t2):
        score += 2
        signals.append('ticker')

    # Name similarity (strip trailing digits to catch "Pool1" vs "Pool2")
    n1 = normalise_name(p1.get('name', ''))
    n2 = normalise_name(p2.get('name', ''))
    if n1 and n2 and n1 == n2:
        score += 2
        signals.append('name')

    # Description match
    desc1 = p1.get('description', '').strip()
    desc2 = p2.get('description', '').strip()
    if desc1 and desc2 and desc1 == desc2:
        score += 1
        signals.append('description')

    return score, signals


def parse_pool_clusters(pool_data, score_threshold=3):
    """
    Clusters pools by operator entity using a multi-signal scoring approach.
    All pools are included in the output keyed by pool hash, since
    map_from_known_clusters looks up by reward address (pool hash).

    Any two pools that score >= score_threshold are placed in the same cluster.
    Transitivity is handled via union-find: if A clusters with B and B with C,
    all three end up in the same cluster.

    All pairs of pools are compared, which means that the complexity is O(n^2)
    but should be fine since it only runs once as a preprocessing step.

    Source for each pool reflects the signals from the comparison that first
    caused it to be clustered, or ['singleton'] if it was never grouped.
    """
    logging.info("Parsing pool clusters..")
    return cluster_by_score(pool_data, score_same_entity, member_key='pool', score_threshold=score_threshold)


if __name__ == '__main__':
    logging.basicConfig(format='[%(asctime)s] %(message)s', datefmt='%Y/%m/%d %I:%M:%S %p', level=logging.INFO)

    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--force-query',
        action='store_true',
        default=False,
        help='Flag to specify whether to query for project data regardless if the relevant data already exist.'
    )
    args = parser.parse_args()

    mapping_info_dir = pathlib.Path(__file__).parent.parent
    pool_data_dir = pathlib.Path(__file__).parent

    pool_data_BQ = get_pool_data_BQ(force_query=args.force_query)
    pool_data_node = get_pool_data_node()

    merged_pool_data = merge_pool_data(pool_data_BQ, pool_data_node)

    identifiers, conflicts = parse_pool_identifiers(merged_pool_data)
    clusters = parse_pool_clusters(merged_pool_data)

    identifiers_dir = mapping_info_dir / 'identifiers'
    with open(identifiers_dir / 'cardano.json', 'w') as f:
        json.dump(identifiers, f, indent=4)

    clusters_dir = mapping_info_dir / 'clusters'
    with open(clusters_dir / 'cardano.json', 'w') as f:
        json.dump(clusters, f, indent=4)

    with open(mapping_info_dir / 'cardano_preprocessing' / 'ticker_conflicts.json', 'w') as f:
        json.dump(conflicts, f, indent=4)

    logging.info(f"Done. {len(identifiers)} identifiers, {len(clusters)} clustered pools, {len(conflicts)} ticker conflicts.")
