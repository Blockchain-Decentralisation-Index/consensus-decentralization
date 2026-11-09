import pytest
from mapping_information.preprocessing_utils import (
    cluster_by_score,
    compare_homepages,
    determine_cluster_name,
    filter_homepage,
    get_domain,
    normalise_name
)


# ---------------------------------------------------------------------------
# filter_homepage
# ---------------------------------------------------------------------------

class TestFilterHomepage:
    def test_valid_url_passes(self):
        assert filter_homepage('https://mypool.io') == 'https://mypool.io'

    def test_strips_whitespace(self):
        assert filter_homepage('  https://mypool.io  ') == 'https://mypool.io'

    def test_empty_string_returns_none(self):
        assert filter_homepage('') is None

    def test_none_returns_none(self):
        assert filter_homepage(None) is None

    def test_na_variants_return_none(self):
        for val in ['n/a', 'N/A', 'NA', 'https://', 'http://', '-', '---', 'TBD', '...']:
            assert filter_homepage(val) is None, f"Expected None for {val!r}"

    def test_placeholder_keywords_return_none(self):
        assert filter_homepage('https://foo.com/pool') is None
        assert filter_homepage('https://example.com') is None
        assert filter_homepage('https://myinvalidurl.io') is None

    def test_coming_soon_returns_none(self):
        assert filter_homepage('Coming Soon') is None

    def test_no_blocked_domains_by_default(self):
        assert filter_homepage('https://x.com/somepool') == 'https://x.com/somepool'

    def test_blocked_domains_rejected(self):
        assert filter_homepage('https://x.com/somepool', blocked_domains={'x.com'}) is None
        assert filter_homepage('https://www.x.com/somepool', blocked_domains={'x.com'}) is None

    def test_blocked_domains_do_not_affect_other_domains(self):
        assert filter_homepage('https://mypool.io', blocked_domains={'x.com'}) == 'https://mypool.io'


# ---------------------------------------------------------------------------
# get_domain
# ---------------------------------------------------------------------------

class TestGetDomain:
    def test_strips_www(self):
        assert get_domain('https://www.mypool.io') == 'mypool.io'

    def test_no_www(self):
        assert get_domain('https://mypool.io') == 'mypool.io'

    def test_with_path(self):
        assert get_domain('https://mypool.io/about') == 'mypool.io'

    def test_empty_string(self):
        assert get_domain('') == ''

    def test_invalid_url(self):
        # Should not raise, returns empty string
        assert get_domain('not a url at all') == ''

    def test_preserves_subdomain(self):
        # The subdomain must survive so two different projects on the same host stay on distinct domains
        assert get_domain('https://site-et7.pages.dev') == 'site-et7.pages.dev'
        assert get_domain('https://other.pages.dev') == 'other.pages.dev'

    def test_path_style_collapses_to_bare_domain(self):
        assert get_domain('https://x.com/alice') == 'x.com'
        assert get_domain('https://x.com/bob') == 'x.com'


# ---------------------------------------------------------------------------
# compare_homepages
# ---------------------------------------------------------------------------

class TestCompareHomepages:
    def test_same_domain(self):
        assert compare_homepages('https://mypool.io', 'https://www.mypool.io/about') == (True, True)

    def test_different_valid_domains(self):
        assert compare_homepages('https://mypool.io', 'https://otherpool.io') == (True, False)

    def test_invalid_homepage(self):
        assert compare_homepages('https://mypool.io', 'n/a') == (False, False)
        assert compare_homepages('', '') == (False, False)

    def test_blocked_domain(self):
        assert compare_homepages('https://x.com/a', 'https://x.com/b') == (True, True)
        assert compare_homepages('https://x.com/a', 'https://x.com/b', blocked_domains={'x.com'}) == (False, False)


# ---------------------------------------------------------------------------
# determine_cluster_name
# ---------------------------------------------------------------------------

class TestDetermineClusterName:
    def test_common_prefix(self):
        assert determine_cluster_name(['Bloom Pool 1', 'Bloom Pool 2', 'Bloom Pool 3']) == 'Bloom Pool'

    def test_no_common_prefix_sorts_alphabetically(self):
        result = determine_cluster_name(['Zeta', 'Alpha', 'Mango'])
        assert result == 'Alpha'

    def test_digit_names_deprioritised(self):
        # Names starting with a digit should come after alphabetic ones
        result = determine_cluster_name(['1ST Pool', 'Alpha Pool'])
        assert result == 'Alpha Pool'

    def test_single_name(self):
        assert determine_cluster_name(['Solo Pool']) == 'Solo Pool'

    def test_empty_names(self):
        assert determine_cluster_name(['', '']) == ''


# ---------------------------------------------------------------------------
# normalise_name
# ---------------------------------------------------------------------------

class TestNormaliseName:
    def test_strips_trailing_digits(self):
        assert normalise_name('Ray Network 1') == 'ray network'
        assert normalise_name('Bloom Pool 42') == 'bloom pool'

    def test_lowercases(self):
        assert normalise_name('RAY NETWORK') == 'ray network'

    def test_strips_whitespace(self):
        assert normalise_name('  Ray Network 1  ') == 'ray network'

    def test_no_digits_lowercased(self):
        assert normalise_name('Ray Network') == 'ray network'

    def test_plural_not_stripped(self):
        # 'Ray Network' and 'Ray Networks' should NOT normalise to the same value
        assert normalise_name('Ray Network') != normalise_name('Ray Networks')

    def test_digits_in_middle_not_stripped(self):
        assert normalise_name('Pool 4 You') == 'pool 4 you'

    def test_numbered_variants_match(self):
        assert normalise_name('Ray Network 1') == normalise_name('Ray Network 2')
        assert normalise_name('ATADA Stakepool Austria 1') == normalise_name('ATADA Stakepool Austria 2')

    def test_different_names_do_not_match(self):
        assert normalise_name('Cardano Pool 1') != normalise_name('Cardano Stake 1')
        assert normalise_name('Tokyo Stake House') != normalise_name('Osaka Block Forge')


# ---------------------------------------------------------------------------
# cluster_by_score
# ---------------------------------------------------------------------------

def _score_by_group(e1, e2):
    """Toy scoring function: entries with the same 'group' score 3, others 0."""
    if e1['group'] == e2['group']:
        return 3, ['group']
    return 0, []


class TestClusterByScore:
    def test_groups_entries_above_threshold(self):
        entries = {
            'id1': {'name': 'Alpha 1', 'group': 'a'},
            'id2': {'name': 'Alpha 2', 'group': 'a'},
            'id3': {'name': 'Beta', 'group': 'b'},
        }
        result = cluster_by_score(entries, _score_by_group, member_key='pool')
        assert result['id1']['cluster'] == result['id2']['cluster'] == 'Alpha'
        assert result['id3']['cluster'] == 'Beta'

    def test_output_fields(self):
        entries = {
            'id1': {'name': 'Alpha 1', 'group': 'a'},
            'id2': {'name': 'Alpha 2', 'group': 'a'},
            'id3': {'name': 'Beta', 'group': 'b'},
        }
        result = cluster_by_score(entries, _score_by_group, member_key='validator')
        assert result['id1'] == {'cluster': 'Alpha', 'validator': 'Alpha 1', 'source': ['group']}
        assert result['id3'] == {'cluster': 'Beta', 'validator': 'Beta', 'source': ['singleton']}

    def test_threshold_respected(self):
        entries = {
            'id1': {'name': 'Alpha 1', 'group': 'a'},
            'id2': {'name': 'Alpha 2', 'group': 'a'},
        }
        result = cluster_by_score(entries, _score_by_group, member_key='pool', score_threshold=4)
        assert result['id1']['source'] == ['singleton']
        assert result['id2']['source'] == ['singleton']

    def test_transitivity(self):
        # A-B and B-C score above threshold, A-C does not: all three still end up together
        def chain_score(e1, e2):
            pair = {e1['name'], e2['name']}
            return (3, ['link']) if pair in ({'A', 'B'}, {'B', 'C'}) else (0, [])
        entries = {'a': {'name': 'A'}, 'b': {'name': 'B'}, 'c': {'name': 'C'}}
        result = cluster_by_score(entries, chain_score, member_key='pool')
        assert result['a']['cluster'] == result['b']['cluster'] == result['c']['cluster']

    def test_custom_name_fn(self):
        entries = {
            'id1': {'name': 'Alpha 1', 'group': 'a'},
            'id2': {'name': 'Alpha 2', 'group': 'a'},
        }
        result = cluster_by_score(entries, _score_by_group, member_key='pool', name_fn=lambda names: 'Custom')
        assert result['id1']['cluster'] == 'Custom'

    def test_empty_input(self):
        assert cluster_by_score({}, _score_by_group, member_key='pool') == {}


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
