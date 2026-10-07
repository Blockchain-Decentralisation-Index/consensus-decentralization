import pytest
from solana_preprocessing import (
    filter_homepage,
    get_domain,
    determine_cluster_name,
    normalise_name,
    score_same_entity,
    parse_validator_clusters,
)


# ---------------------------------------------------------------------------
# filter_homepage
# ---------------------------------------------------------------------------

class TestFilterHomepage:
    def test_valid_url_passes(self):
        assert filter_homepage('https://myvalidator.io') == 'https://myvalidator.io'

    def test_strips_whitespace(self):
        assert filter_homepage('  https://myvalidator.io  ') == 'https://myvalidator.io'

    def test_empty_string_returns_none(self):
        assert filter_homepage('') is None

    def test_none_returns_none(self):
        assert filter_homepage(None) is None

    def test_na_variants_return_none(self):
        for val in ['n/a', 'N/A', 'NA', 'https://', 'http://', '-', '---', 'TBD', '...']:
            assert filter_homepage(val) is None, f"Expected None for {val!r}"

    def test_placeholder_keywords_return_none(self):
        assert filter_homepage('https://foo.com/validator') is None
        assert filter_homepage('https://example.com') is None

    # --- Solana-specific: path-style platforms are rejected ------------------
    def test_path_style_platforms_rejected(self):
        # Identity lives in the URL path, so get_domain() collapses every user
        # onto the same bare domain -> would falsely group unrelated validators.
        for url in [
            'https://x.com/somevalidator',
            'https://twitter.com/somevalidator',
            'https://github.com/somevalidator',
            'https://keybase.io/somevalidator',
            'https://t.me/somechannel',
            'https://linktr.ee/somevalidator',
            'https://stakewiz.com/validator/abc',
        ]:
            assert filter_homepage(url) is None, f"Expected None for path-style {url!r}"

    # --- Solana-specific: subdomain-style hosts are NOT rejected -------------
    def test_subdomain_style_hosts_pass(self):
        # Identity lives in the subdomain, which get_domain() preserves, so
        # distinct projects get distinct domains -> a genuine signal.
        for url in [
            'https://site-et7.pages.dev',
            'https://myvalidator.github.io',
            'https://myvalidator.netlify.app',
            'https://myvalidator.vercel.app',
        ]:
            assert filter_homepage(url) == url, f"Expected {url!r} to pass"


# ---------------------------------------------------------------------------
# get_domain
# ---------------------------------------------------------------------------

class TestGetDomain:
    def test_strips_www(self):
        assert get_domain('https://www.myvalidator.io') == 'myvalidator.io'

    def test_no_www(self):
        assert get_domain('https://myvalidator.io') == 'myvalidator.io'

    def test_with_path(self):
        assert get_domain('https://myvalidator.io/about') == 'myvalidator.io'

    def test_empty_string(self):
        assert get_domain('') == ''

    def test_invalid_url(self):
        assert get_domain('not a url at all') == ''

    def test_preserves_subdomain(self):
        # Critical for the subdomain-style logic: the subdomain must survive so
        # two different projects on the same host stay on distinct domains.
        assert get_domain('https://site-et7.pages.dev') == 'site-et7.pages.dev'
        assert get_domain('https://other.pages.dev') == 'other.pages.dev'

    def test_path_style_collapses_to_bare_domain(self):
        # The flip side: path-style hosts collapse to one domain (hence blacklist).
        assert get_domain('https://x.com/alice') == 'x.com'
        assert get_domain('https://x.com/bob') == 'x.com'


# ---------------------------------------------------------------------------
# determine_cluster_name
# ---------------------------------------------------------------------------

class TestDetermineClusterName:
    def test_common_prefix_whole_word(self):
        assert determine_cluster_name(['Bloom Pool 1', 'Bloom Pool 2', 'Bloom Pool 3']) == 'Bloom Pool'

    def test_stray_shared_letter_falls_back_to_first_word(self):
        # "Sunren" + "Solana Vibe Station" share only "S"; the guard rejects
        # that fragment and uses the first word of the alphabetically-first name.
        assert determine_cluster_name(['SUNREN', 'Solana Vibe Station']) == 'Solana'

    def test_no_common_prefix_uses_first_word_alphabetically(self):
        assert determine_cluster_name(['Zeta Validator', 'Alpha Node', 'Mango Stake']) == 'Alpha'

    def test_digit_boundary_prefix_kept(self):
        # "Kiln1"/"Kiln2" share "Kiln" with only trailing digits after it.
        assert determine_cluster_name(['Kiln1', 'Kiln2']) == 'Kiln'

    def test_prefix_equal_to_full_name_kept(self):
        assert determine_cluster_name(['Coinbase', 'Coinbase 02', 'Coinbase 03']) == 'Coinbase'

    def test_digit_names_deprioritised(self):
        assert determine_cluster_name(['1ST Node', 'Alpha Pool']) == 'Alpha'

    def test_single_name_kept_whole(self):
        assert determine_cluster_name(['Solo Validator']) == 'Solo Validator'


# ---------------------------------------------------------------------------
# normalise_name
# ---------------------------------------------------------------------------

class TestNormaliseName:
    def test_strips_trailing_digits(self):
        assert normalise_name('Kraken 1') == 'kraken'
        assert normalise_name('Temporal 42') == 'temporal'

    def test_lowercases(self):
        assert normalise_name('KRAKEN') == 'kraken'

    def test_strips_whitespace(self):
        assert normalise_name('  Kraken 1  ') == 'kraken'

    def test_no_digits_lowercased(self):
        assert normalise_name('Kraken') == 'kraken'

    def test_plural_not_stripped(self):
        assert normalise_name('Node') != normalise_name('Nodes')

    def test_digits_in_middle_not_stripped(self):
        assert normalise_name('Pool 4 You') == 'pool 4 you'

    def test_numbered_variants_match(self):
        assert normalise_name('Kraken 1') == normalise_name('Kraken 2')

    def test_different_names_do_not_match(self):
        assert normalise_name('U1S1 Validator') != normalise_name('Moutai Validator')


# ---------------------------------------------------------------------------
# score_same_entity  (two signals only: homepage +3, name +2; no penalty)
# ---------------------------------------------------------------------------

class TestScoreSameEntity:
    def _v(self, name='', homepage=''):
        return {'name': name, 'homepage': homepage}

    def test_same_homepage_and_name_scores_5(self):
        v1 = self._v(name='Kraken', homepage='https://kraken.com')
        v2 = self._v(name='Kraken', homepage='https://kraken.com')
        score, signals = score_same_entity(v1, v2)
        assert score == 5
        assert signals == ['homepage', 'name']

    def test_same_homepage_only_scores_3(self):
        v1 = self._v(name='Alpha', homepage='https://shared.io')
        v2 = self._v(name='Beta', homepage='https://shared.io')
        score, signals = score_same_entity(v1, v2)
        assert score == 3
        assert signals == ['homepage']

    def test_same_name_only_scores_2(self):
        v1 = self._v(name='Repeated Name', homepage='https://a.io')
        v2 = self._v(name='Repeated Name', homepage='https://b.io')
        score, signals = score_same_entity(v1, v2)
        assert score == 2
        assert signals == ['name']

    def test_different_domains_no_penalty(self):
        # KEY difference from Cardano: two distinct valid domains + distinct
        # names score 0 with NO -1 penalty.
        v1 = self._v(name='Alpha', homepage='https://a.io')
        v2 = self._v(name='Beta', homepage='https://b.io')
        score, signals = score_same_entity(v1, v2)
        assert score == 0
        assert signals == []

    def test_path_style_homepage_does_not_contribute(self):
        # Both on x.com but different users -> filtered out -> no homepage signal.
        v1 = self._v(name='Alpha', homepage='https://x.com/alpha')
        v2 = self._v(name='Beta', homepage='https://x.com/beta')
        score, signals = score_same_entity(v1, v2)
        assert score == 0
        assert signals == []

    def test_subdomain_style_same_subdomain_contributes(self):
        v1 = self._v(name='U1S1', homepage='https://site-et7.pages.dev')
        v2 = self._v(name='Moutai', homepage='https://site-et7.pages.dev')
        score, signals = score_same_entity(v1, v2)
        assert score == 3
        assert signals == ['homepage']

    def test_subdomain_style_different_subdomain_no_contribution(self):
        v1 = self._v(name='Alpha', homepage='https://alpha.pages.dev')
        v2 = self._v(name='Beta', homepage='https://beta.pages.dev')
        score, signals = score_same_entity(v1, v2)
        assert score == 0
        assert signals == []

    def test_dummy_homepage_no_contribution(self):
        v1 = self._v(name='Alpha', homepage='n/a')
        v2 = self._v(name='Beta', homepage='https://valid.io')
        score, signals = score_same_entity(v1, v2)
        assert score == 0
        assert signals == []


# ---------------------------------------------------------------------------
# parse_validator_clusters
# ---------------------------------------------------------------------------

class TestParseValidatorClusters:
    def test_shared_homepage_clusters_together(self):
        validators = {
            'vote1': {'name': 'Alpha', 'homepage': 'https://shared.io'},
            'vote2': {'name': 'Beta', 'homepage': 'https://shared.io'},
            'vote3': {'name': 'Other', 'homepage': 'https://other.io'},
        }
        clusters = parse_validator_clusters(validators)
        assert clusters['vote1']['cluster'] == clusters['vote2']['cluster']
        assert clusters['vote1']['source'] == ['homepage']
        assert clusters['vote2']['source'] == ['homepage']
        assert clusters['vote3']['source'] == ['singleton']

    def test_no_shared_signal_all_singletons(self):
        validators = {
            'vote1': {'name': 'Alpha', 'homepage': 'https://a.io'},
            'vote2': {'name': 'Beta', 'homepage': 'https://b.io'},
        }
        clusters = parse_validator_clusters(validators)
        assert clusters['vote1']['source'] == ['singleton']
        assert clusters['vote2']['source'] == ['singleton']
        assert clusters['vote1']['cluster'] != clusters['vote2']['cluster']

    def test_transitivity_three_share_one_cluster(self):
        # A-B and B-C both share the same homepage -> all three in one cluster.
        validators = {
            'voteA': {'name': 'A Node', 'homepage': 'https://chain.io'},
            'voteB': {'name': 'B Node', 'homepage': 'https://chain.io'},
            'voteC': {'name': 'C Node', 'homepage': 'https://chain.io'},
        }
        clusters = parse_validator_clusters(validators)
        names = {clusters['voteA']['cluster'], clusters['voteB']['cluster'], clusters['voteC']['cluster']}
        assert len(names) == 1

    def test_name_alone_does_not_group(self):
        # Same name but different domains -> score 2 < threshold 3 -> singletons.
        validators = {
            'vote1': {'name': 'Validator', 'homepage': 'https://a.io'},
            'vote2': {'name': 'Validator', 'homepage': 'https://b.io'},
        }
        clusters = parse_validator_clusters(validators)
        assert clusters['vote1']['source'] == ['singleton']
        assert clusters['vote2']['source'] == ['singleton']

    def test_path_style_platform_does_not_group(self):
        validators = {
            'vote1': {'name': 'Alpha', 'homepage': 'https://x.com/alpha'},
            'vote2': {'name': 'Beta', 'homepage': 'https://x.com/beta'},
        }
        clusters = parse_validator_clusters(validators)
        assert clusters['vote1']['source'] == ['singleton']
        assert clusters['vote2']['source'] == ['singleton']

    def test_subdomain_style_same_subdomain_groups(self):
        validators = {
            'vote1': {'name': 'U1S1', 'homepage': 'https://site-et7.pages.dev'},
            'vote2': {'name': 'Moutai', 'homepage': 'https://site-et7.pages.dev'},
        }
        clusters = parse_validator_clusters(validators)
        assert clusters['vote1']['cluster'] == clusters['vote2']['cluster']
        assert clusters['vote1']['source'] == ['homepage']

    def test_subdomain_style_different_subdomain_does_not_group(self):
        validators = {
            'vote1': {'name': 'Alpha', 'homepage': 'https://alpha.pages.dev'},
            'vote2': {'name': 'Beta', 'homepage': 'https://beta.pages.dev'},
        }
        clusters = parse_validator_clusters(validators)
        assert clusters['vote1']['cluster'] != clusters['vote2']['cluster']
        assert clusters['vote1']['source'] == ['singleton']
        assert clusters['vote2']['source'] == ['singleton']

    def test_homepage_and_name_source(self):
        # Same domain AND same normalised name -> source carries both signals.
        validators = {
            'vote1': {'name': 'Kraken', 'homepage': 'https://kraken.com'},
            'vote2': {'name': 'Kraken 2', 'homepage': 'https://kraken.com'},
        }
        clusters = parse_validator_clusters(validators)
        assert clusters['vote1']['cluster'] == clusters['vote2']['cluster']
        assert clusters['vote1']['source'] == ['homepage', 'name']

    def test_output_keyed_by_vote_account_with_validator_field(self):
        validators = {
            'voteXYZ': {'name': 'Solo', 'homepage': 'https://solo.io'},
        }
        clusters = parse_validator_clusters(validators)
        assert 'voteXYZ' in clusters
        assert clusters['voteXYZ']['validator'] == 'Solo'
        assert 'cluster' in clusters['voteXYZ']
        assert 'source' in clusters['voteXYZ']


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
