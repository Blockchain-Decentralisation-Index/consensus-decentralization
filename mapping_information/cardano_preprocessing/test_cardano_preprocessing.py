import pytest
from mapping_information.cardano_preprocessing.cardano_preprocessing import (
    merge_pool_data,
    parse_pool_identifiers,
    score_same_entity,
    parse_pool_clusters,
    normalise_ticker
)


# ---------------------------------------------------------------------------
# merge_pool_data
# ---------------------------------------------------------------------------

class TestMergePoolData:
    def _bq(self):
        return {
            'hash_abc': {'ticker': 'POOL', 'name': 'My Pool', 'homepage': 'https://pool.io', 'description': 'A pool'},
            'hash_xyz': {'ticker': 'OTHER', 'name': 'Other Pool', 'homepage': 'https://other.io', 'description': 'B pool'},
        }

    def _node(self):
        return {
            'hash_abc': {'ticker': 'POOL', 'name': 'My Pool', 'homepage': 'https://pool.io', 'description': 'A pool'},
            'hash_new': {'ticker': 'NEW', 'name': 'New Pool', 'homepage': 'https://new.io', 'description': 'C pool'},
        }

    def test_total_count(self):
        result = merge_pool_data(self._bq(), self._node())
        assert len(result) == 3

    def test_matched_pool_present(self):
        result = merge_pool_data(self._bq(), self._node())
        assert 'hash_abc' in result

    def test_bq_only_pool_present(self):
        result = merge_pool_data(self._bq(), self._node())
        assert 'hash_xyz' in result

    def test_node_only_pool_present(self):
        result = merge_pool_data(self._bq(), self._node())
        assert 'hash_new' in result


# ---------------------------------------------------------------------------
# parse_pool_identifiers
# ---------------------------------------------------------------------------

class TestParsePoolIdentifiers:
    def test_unique_tickers_all_present(self):
        pool_data = {
            'hash1': {'ticker': 'AAA', 'name': 'Alpha', 'homepage': 'https://alpha.io'},
            'hash2': {'ticker': 'BBB', 'name': 'Beta', 'homepage': 'https://beta.io'}
        }
        identifiers, conflicts = parse_pool_identifiers(pool_data)
        assert 'AAA' in identifiers
        assert 'BBB' in identifiers
        assert len(identifiers) == 2
        assert len(conflicts) == 0

    def test_same_ticker_same_domain_no_conflict(self):
        # Two pools with the same ticker pointing to the same domain → no conflict
        pool_data = {
            'hash1': {'ticker': 'MULTI', 'name': 'Pool 1', 'homepage': 'https://multi.io'},
            'hash2': {'ticker': 'MULTI', 'name': 'Pool 2', 'homepage': 'https://multi.io'}
        }
        identifiers, conflicts = parse_pool_identifiers(pool_data)
        assert len(identifiers) == 1
        assert 'MULTI' not in conflicts

    def test_same_ticker_different_domain_is_conflict(self):
        pool_data = {
            'hash1': {'ticker': 'ANIME', 'name': 'Anime Pool A', 'homepage': 'https://animea.io'},
            'hash2': {'ticker': 'ANIME', 'name': 'Anime Pool B', 'homepage': 'https://animeb.io'},
        }
        identifiers, conflicts = parse_pool_identifiers(pool_data)
        assert 'ANIME' in conflicts
        assert len(identifiers) == 0  # should not include the conflicting ticker
        assert len(conflicts['ANIME']) == 2

    def test_missing_ticker_ignored(self):
        pool_data = {
            'hash1': {'ticker': '', 'name': 'No Ticker', 'homepage': 'https://noticker.io'},
            'hash2': {'ticker': 'OK', 'name': 'Has Ticker', 'homepage': 'https://ok.io'},
        }
        identifiers, conflicts = parse_pool_identifiers(pool_data)
        assert len(identifiers) == 1
        assert 'OK' in identifiers


# ---------------------------------------------------------------------------
# score_same_entity
# ---------------------------------------------------------------------------

class TestScoreSameEntity:
    def _pool(self, ticker='', name='', homepage='', description=''):
        return {'ticker': ticker, 'name': name, 'homepage': homepage, 'description': description}

    def test_identical_pools_score_high(self):
        p1 = self._pool(ticker='SAME', name='Same Pool', homepage='https://same.io', description='A pool')
        p2 = self._pool(ticker='SAME', name='Same Pool', homepage='https://same.io', description='A pool')
        score, signals = score_same_entity(p1, p2)
        assert score == 8
        assert [signal in signals for signal in ['ticker', 'name', 'homepage', 'description']]
        assert len(signals) == 4

    def test_same_domain_contributes_3(self):
        p1 = self._pool(ticker='AAA', homepage='https://mypool.io')
        p2 = self._pool(ticker='BBB', name='Other Pool', homepage='https://mypool.io', description='different')
        score, signals = score_same_entity(p1, p2)
        assert score == 3
        assert 'homepage' in signals
        assert len(signals) == 1

    def test_same_ticker_contributes_2(self):
        p1 = self._pool(ticker='SAME')
        p2 = self._pool(ticker='SAME')
        score, signals = score_same_entity(p1, p2)
        assert score == 2
        assert 'ticker' in signals
        assert len(signals) == 1

    def test_similar_ticker_contributes_2(self):
        p1 = self._pool(ticker='SAME1')
        p2 = self._pool(ticker='SAME2')
        score, signals = score_same_entity(p1, p2)
        assert score == 2
        assert 'ticker' in signals
        assert len(signals) == 1

    def test_same_ticker_different_real_domains_penalised(self):
        p1 = self._pool(ticker='ANIME', name='Tokyo Stake House', homepage='https://animea.io', description='')
        p2 = self._pool(ticker='ANIME', name='Osaka Block Forge', homepage='https://animeb.io', description='')
        score, signals = score_same_entity(p1, p2)
        assert score == 1

    def test_dummy_homepage_no_domain_penalty(self):
        # If one pool has n/a homepage, domain penalty should not apply.
        # Use distinct names so name similarity doesn't contribute.
        p1 = self._pool(ticker='LOVE', name='Stakehouse Alpha', homepage='n/a', description='')
        p2 = self._pool(ticker='LOVE', name='Riverfront Beta', homepage='https://love.io', description='')
        score, signals = score_same_entity(p1, p2)
        assert score == 2
        assert 'ticker' in signals
        assert len(signals) == 1

    def test_similar_names_contribute(self):
        p1 = self._pool(name='Bloom Pool 1')
        p2 = self._pool(name='Bloom Pool 2')
        score, signals = score_same_entity(p1, p2)
        assert score == 2
        assert 'name' in signals
        assert len(signals) == 1

    def test_similar_names_and_tickers_contribute(self):
        p1 = self._pool(name='Bloom Pool 1', ticker='BLM1')
        p2 = self._pool(name='Bloom Pool 2', ticker='BLM2')
        score, signals = score_same_entity(p1, p2)
        assert score == 4
        assert 'name' in signals and 'ticker' in signals
        assert len(signals) == 2

    def test_similar_names_and_tickers_but_homepage_penalty(self):
        p1 = self._pool(name='Bloom Pool 1', ticker='BLM1', homepage='https://bloom1.io')
        p2 = self._pool(name='Bloom Pool 2', ticker='BLM2', homepage='https://bloom2.io')
        score, signals = score_same_entity(p1, p2)
        assert score == 3
        assert 'name' in signals and 'ticker' in signals
        assert len(signals) == 2

    def test_same_description_contributes_1(self):
        p1 = self._pool(ticker='X', description='shared desc')
        p2 = self._pool(ticker='Y', description='shared desc')
        score, signals = score_same_entity(p1, p2)
        assert score == 1
        assert 'description' in signals
        assert len(signals) == 1

    def test_no_homepage_penalty_if_one_is_dummy(self):
        p1 = self._pool(ticker='X', homepage='n/a')
        p2 = self._pool(ticker='X', homepage='https://valid.io')
        score, signals = score_same_entity(p1, p2)
        assert score == 2
        assert 'ticker' in signals
        assert len(signals) == 1


# ---------------------------------------------------------------------------
# parse_pool_clusters
# ---------------------------------------------------------------------------

class TestParsePoolClusters:
    def test_same_domain_clusters_together(self):
        pools = {
            'hash1': {'ticker': 'BLM1', 'name': 'Bloom 1', 'homepage': 'https://bloom.io', 'description': ''},
            'hash2': {'ticker': 'BLM2', 'name': 'Bloom 2', 'homepage': 'https://bloom.io', 'description': ''},
            'hash3': {'ticker': 'OTHER', 'name': 'Other', 'homepage': 'https://other.io', 'description': ''},
        }
        clusters = parse_pool_clusters(pools)
        assert 'hash1' in clusters
        assert 'hash2' in clusters
        assert clusters['hash1']['cluster'] == clusters['hash2']['cluster']
        assert clusters['hash1']['source'] == ['homepage', 'ticker', 'name']
        assert clusters['hash2']['source'] == ['homepage', 'ticker', 'name']
        assert 'hash3' in clusters
        assert clusters['hash3']['source'] == ['singleton']

    def test_different_domains_same_ticker_included_as_singletons(self):
        pools = {
            'hash1': {'ticker': 'ANIME', 'name': 'Tokyo Stake House', 'homepage': 'https://animea.io', 'description': ''},
            'hash2': {'ticker': 'ANIME', 'name': 'Osaka Block Forge', 'homepage': 'https://animeb.io', 'description': ''},
        }
        clusters = parse_pool_clusters(pools)
        assert 'hash1' in clusters
        assert 'hash2' in clusters
        assert clusters['hash1']['cluster'] != clusters['hash2']['cluster']
        assert clusters['hash1']['source'] == ['singleton']
        assert clusters['hash2']['source'] == ['singleton']

    def test_na_homepage_not_clustered_together(self):
        pools = {
            'hash1': {'ticker': 'POOL', 'name': 'Pool', 'homepage': 'n/a', 'description': ''},
            'hash2': {'ticker': 'PEEL', 'name': 'Peel', 'homepage': 'n/a', 'description': ''},
        }
        clusters = parse_pool_clusters(pools)
        assert clusters['hash1']['source'] == ['singleton']
        assert clusters['hash2']['source'] == ['singleton']
        assert clusters['hash1']['cluster'] != clusters['hash2']['cluster']

    def test_cluster_name_uses_common_prefix(self):
        pools = {
            'hash1': {'ticker': 'RAY1', 'name': 'Ray Network 1', 'homepage': 'https://ray.io', 'description': ''},
            'hash2': {'ticker': 'RAY2', 'name': 'Ray Network 2', 'homepage': 'https://ray.io', 'description': ''},
            'hash3': {'ticker': 'RAY3', 'name': 'Ray Network 3', 'homepage': 'https://ray.io', 'description': ''},
        }
        clusters = parse_pool_clusters(pools)
        assert 'Ray Network' in clusters['hash1']['cluster']

    def test_multi_signal_source_when_no_shared_domain(self):
        pools = {
            'hash1': {'ticker': 'LOVE', 'name': 'Love Pool 1', 'homepage': 'https://love1.io', 'description': 'shared desc'},
            'hash2': {'ticker': 'LOVE', 'name': 'Love Pool 2', 'homepage': 'https://love2.io', 'description': 'shared desc'},
        }
        clusters = parse_pool_clusters(pools)
        assert 'hash1' in clusters
        assert 'hash2' in clusters
        assert clusters['hash1']['source'] == ['ticker', 'name', 'description']
        assert clusters['hash2']['source'] == ['ticker', 'name', 'description']
        assert clusters['hash1']['cluster'] == clusters['hash2']['cluster']

    def test_mixed_source_homepage_pool_keeps_homepage_source(self):
        pools = {
            'hash1': {'ticker': 'RAY', 'name': 'Ray Network 1', 'homepage': 'https://ray.io', 'description': 'Ray pool'},
            'hash2': {'ticker': 'RAY', 'name': 'Ray Network 2', 'homepage': 'https://ray.io', 'description': 'Ray pool'},
            'hash3': {'ticker': 'RAY', 'name': 'Ray Network 3', 'homepage': 'https://ray-extra.io', 'description': 'Ray pool'},
        }
        clusters = parse_pool_clusters(pools)
        assert clusters.get('hash1', {}).get('source') == ['homepage', 'ticker', 'name', 'description']
        assert clusters.get('hash2', {}).get('source') == ['homepage', 'ticker', 'name', 'description']
        assert clusters['hash3']['source'] == ['ticker', 'name', 'description']
        assert clusters['hash1']['cluster'] == clusters['hash3']['cluster']


# ---------------------------------------------------------------------------
# normalise_ticker
# ---------------------------------------------------------------------------


class TestNormaliseTicker:
    def test_strips_trailing_digits(self):
        assert normalise_ticker('RAY1') == 'RAY'
        assert normalise_ticker('BLOOM42') == 'BLOOM'

    def test_no_digits_unchanged(self):
        assert normalise_ticker('RAY') == 'RAY'

    def test_uppercases(self):
        assert normalise_ticker('ray1') == 'RAY'

    def test_strips_whitespace(self):
        assert normalise_ticker('  RAY1  ') == 'RAY'

    def test_only_digits_unchanged(self):
        assert normalise_ticker('123') == '123'

    def test_digits_in_middle_unchanged(self):
        # digits not at the end should not be stripped
        assert normalise_ticker('R4Y') == 'R4Y'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
