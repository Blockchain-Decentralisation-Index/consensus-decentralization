import datetime
import argparse
import shutil
import pytest
from unittest.mock import patch, Mock
import requests
import consensus_decentralization.helper as hlp
from consensus_decentralization.helper import get_pool_identifiers, get_pool_legal_links, get_known_addresses, \
    get_pool_clusters, write_blocks_per_entity_to_file, get_blocks_per_entity_from_file, get_timeframe_beginning, \
    get_timeframe_end, get_time_period, get_ledgers, valid_date, INTERIM_DIR, get_blocks_per_entity_filename, \
    get_representative_dates
from consensus_decentralization.map import ledger_mapping


@pytest.fixture
def setup_and_cleanup():
    """
    This function can be used to set up the right conditions for a test and also clean up after the test is finished.
    The part before the yield command is run before the test (setup) and the part after the yield command is run
    after (cleanup)
    """
    # Setting up
    test_output_dir = INTERIM_DIR / "test_output"
    test_output_dir.mkdir(parents=True, exist_ok=True)
    yield test_output_dir
    # Cleaning up
    shutil.rmtree(test_output_dir)


def test_pool_data():
    pool_identifiers = get_pool_identifiers(project_name='test')
    pool_addresses = get_known_addresses(project_name='test')
    pool_clusters = get_pool_clusters(project_name='test')
    legal_links = get_pool_legal_links(timeframe='2022')

    assert all([
        legal_links['AntPool'] == 'Bitmain',
        legal_links['NovaBlock'] == 'Poolin',
        legal_links['BTC.COM'] == 'BIT Mining',
        legal_links['Bitdeer'] == 'BIT Mining'
    ])

    assert all([
        pool_identifiers['entity 1']['name'] == 'Entity 1',
        pool_identifiers['entity 1']['link'] == 'https://www.entity.1',
        pool_identifiers['ent2']['name'] == 'Entity 2',
        pool_identifiers['ent2']['link'] == 'https://www.entity.2',
        pool_identifiers['entity_3']['name'] == 'Entity 3',
        pool_identifiers['entity_3']['link'] == 'https://www.entity.3',
        pool_identifiers['entity 4']['name'] == 'Entity 4',
        pool_identifiers['entity 4']['link'] == 'https://www.entity.4',
        pool_identifiers['entity_5']['name'] == 'Entity 5',
        pool_identifiers['entity_5']['link'] == 'https://www.entity.5'
    ])

    assert all([
        pool_addresses['address1'] == "Entity 4",
        pool_addresses['addr2'] == "Entity 5"
    ])

    assert all([
        pool_clusters['pool_hash_1']['cluster'] == 'cluster 1',
        pool_clusters['pool_hash_2']['cluster'] == 'cluster 1',
        pool_clusters['pool_hash_3']['cluster'] == 'cluster 2'
    ])

    legal_links = get_pool_legal_links(timeframe='2021-03-12')
    assert all([
        legal_links['AntPool'] == 'Bitmain',
        legal_links['NovaBlock'] == 'Poolin',
        legal_links['BTC.COM'] == 'Bitdeer'
    ])


def test_committed_pool_data():
    for project_name in ledger_mapping.keys() - ['sample_bitcoin', 'sample_ethereum', 'sample_cardano', 'sample_tezos']:
        get_pool_identifiers(project_name)
        get_known_addresses(project_name)
        for year in range(2018, 2024):
            get_pool_legal_links(timeframe=str(year))
            for month in range(1, 13):
                get_pool_legal_links(timeframe=f'{year}-{month:02d}')


def test_write_read_blocks_per_entity(setup_and_cleanup):
    output_dir = setup_and_cleanup

    blocks_per_entity = {
        'Entity 1': {'2018': 1, '2019': 3, '2020': 2, '2021': 3},
        'Entity 2': {'2018': 2, '2019': 2, '2021': 1},
        'Entity 3': {'2018': 2},
        'Entity 4': {'2021': 1}
    }

    write_blocks_per_entity_to_file(output_dir=output_dir, blocks_per_entity=blocks_per_entity,
                                    dates=['2018', '2019', '2020', '2021'], filename='test.csv')

    dates, bpe = get_blocks_per_entity_from_file(output_dir / 'test.csv', population_windows=1)

    assert dates == ['2018', '2019', '2020', '2021']
    assert all([
        bpe['Entity 1'] == {'2018': 1, '2019': 3, '2020': 2, '2021': 3},
        bpe['Entity 2'] == {'2018': 2, '2019': 2, '2020': 0, '2021': 1},
        bpe['Entity 3'] == {'2018': 2, '2019': 0},
        bpe['Entity 4'] == {'2020': 0, '2021': 1}
    ])


def test_valid_date():
    for d in ['2022', '2022-01', '2022-01-01']:
        assert valid_date(d)

    for d in ['2022/1/01', '2022/01/1', '2022/1', '2022/01', '2022.1.01', '2022.01.1', '2022.1', '2022.01', 'blah',
              '2022-', '2022-1-1', '2022-1-01', '2022-1', '2022-01-1', '2022-02-29']:
        with pytest.raises(argparse.ArgumentTypeError) as e_info:
            valid_date(d)
        assert e_info.type == argparse.ArgumentTypeError


def test_get_start_date():  # currently not testing for invalid dates
    dates = {'2022': datetime.date(2022, 1, 1), '2022-03': datetime.date(2022, 3, 1),
             '2022-03-29': datetime.date(2022, 3, 29)}
    for date, start_date in dates.items():
        assert get_timeframe_beginning(date) == start_date


def test_get_timeframe_end():  # currently not testing for invalid dates
    dates = {'2022': datetime.date(2022, 12, 31), '2022-03': datetime.date(2022, 3, 31),
             '2022-03-29': datetime.date(2022, 3, 29)}
    for date, end_date in dates.items():
        assert get_timeframe_end(date) == end_date


def test_get_time_period():  # currently not testing for invalid dates
    from_to = [('2018', '2022'), ('2018-01-23', '2022-03'), ('2018-06', '2019-01'), ('', '2019-03-09'),
               ('2019-02-09', '')]
    time_periods = [(datetime.date(2018, 1, 1), datetime.date(2021, 12, 31)),
                    (datetime.date(2018, 1, 23), datetime.date(2022, 2, 28)),
                    (datetime.date(2018, 6, 1), datetime.date(2018, 12, 31)),
                    (datetime.date(1, 1, 1), datetime.date(2019, 3, 8)),
                    (datetime.date(2019, 2, 9), datetime.date(9999, 12, 31))]

    for i, (frm, to) in enumerate(from_to):
        assert get_time_period(frm, to) == time_periods[i]


def test_get_ledgers():
    ledgers = get_ledgers()
    assert isinstance(ledgers, list)
    assert len(ledgers) > 0


def test_get_blocks_per_entity_filename():
    timeframe = (datetime.date(2022, 1, 1), datetime.date(2022, 12, 31))
    estimation_window = 30
    frequency = 7
    filename = get_blocks_per_entity_filename(timeframe, estimation_window, frequency)
    assert filename == '30_day_window_from_2022-01-01_to_2022-12-31_sampled_every_7_days.csv'

    estimation_window = None
    frequency = None
    filename = get_blocks_per_entity_filename(timeframe, estimation_window, frequency)
    assert filename == 'all_from_2022-01-01_to_2022-12-31.csv'


def test_get_representative_dates():
    time_chunks = [
        (datetime.date(2022, 1, 1), datetime.date(2022, 1, 30)),
        (datetime.date(2022, 1, 31), datetime.date(2022, 3, 2)),
        (datetime.date(2022, 3, 3), datetime.date(2022, 4, 2))
        ]
    representative_dates = get_representative_dates(time_chunks)
    assert representative_dates == ['2022-01-15', '2022-02-15', '2022-03-18']

    time_chunks = [
        (datetime.date(2022, 1, 1), datetime.date(2022, 1, 1)),
        (datetime.date(2022, 1, 2), datetime.date(2022, 1, 2)),
        (datetime.date(2022, 1, 3), datetime.date(2022, 1, 3))
        ]
    representative_dates = get_representative_dates(time_chunks)
    assert representative_dates == ['2022-01-01', '2022-01-02', '2022-01-03']

    time_chunks = [
        (datetime.date(2022, 1, 1), datetime.date(2022, 12, 31)),
        (datetime.date(2023, 1, 1), datetime.date(2023, 12, 31)),
        (datetime.date(2024, 1, 1), datetime.date(2024, 12, 31))
        ]
    representative_dates = get_representative_dates(time_chunks)
    assert representative_dates == ['2022-07-02', '2023-07-02', '2024-07-01']


def test_get_input_directories(tmp_path, monkeypatch):
    monkeypatch.setattr(hlp, 'IPFS_CACHE_DIR', tmp_path)
    monkeypatch.setattr(hlp, 'config', {
        'ledgers': ['bitcoin', 'ethereum'],
        'input_directories': ['raw_block_data', 'ipfs://testcid'],
    })

    mock_response = Mock(content=b'{"number": 1}\n')
    with patch('consensus_decentralization.helper.requests.get', return_value=mock_response) as mock_get:
        dirs = hlp.get_input_directories()

    ipfs_dir = tmp_path / 'testcid'
    assert dirs == [hlp.ROOT_DIR / 'raw_block_data', ipfs_dir]
    assert (ipfs_dir / 'bitcoin_raw_data.json').read_bytes() == b'{"number": 1}\n'
    assert (ipfs_dir / 'ethereum_raw_data.json').is_file()
    assert mock_get.call_count == 2
    mock_get.assert_any_call('https://ipfs.io/ipfs/testcid/bitcoin_raw_data.json', timeout=60)

    # Cached files should not be re-fetched on subsequent calls
    with patch('consensus_decentralization.helper.requests.get', return_value=mock_response) as mock_get_again:
        hlp.get_input_directories()
    assert mock_get_again.call_count == 0


def test_get_input_directories_skips_missing_ledger_data(tmp_path, monkeypatch):
    monkeypatch.setattr(hlp, 'IPFS_CACHE_DIR', tmp_path)
    monkeypatch.setattr(hlp, 'config', {
        'ledgers': ['bitcoin'],
        'input_directories': ['ipfs://testcid'],
    })

    with patch('consensus_decentralization.helper.requests.get', side_effect=requests.RequestException('not found')):
        dirs = hlp.get_input_directories()

    assert not (dirs[0] / 'bitcoin_raw_data.json').exists()


def test_get_input_directories_falls_back_to_next_gateway(tmp_path, monkeypatch):
    monkeypatch.setattr(hlp, 'IPFS_CACHE_DIR', tmp_path)
    monkeypatch.setattr(hlp, 'config', {
        'ledgers': ['bitcoin'],
        'input_directories': ['ipfs://testcid'],
        'ipfs_gateway': ['https://unreachable.example', 'http://127.0.0.1:8080'],
    })

    mock_response = Mock(content=b'{"number": 1}\n')
    with patch('consensus_decentralization.helper.requests.get',
               side_effect=[requests.RequestException('unreachable'), mock_response]) as mock_get:
        dirs = hlp.get_input_directories()

    assert (dirs[0] / 'bitcoin_raw_data.json').read_bytes() == b'{"number": 1}\n'
    assert mock_get.call_count == 2
    mock_get.assert_any_call('https://unreachable.example/ipfs/testcid/bitcoin_raw_data.json', timeout=60)
    mock_get.assert_any_call('http://127.0.0.1:8080/ipfs/testcid/bitcoin_raw_data.json', timeout=60)
