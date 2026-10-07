import pathlib
import pytest
import shutil
import os
import json
from consensus_decentralization.parse import parse, ledger_parser
from consensus_decentralization.parsers.default_parser import DefaultParser
from consensus_decentralization.parsers.dummy_parser import DummyParser
from consensus_decentralization.parsers.ethereum_parser import EthereumParser
from consensus_decentralization.map import apply_mapping, ledger_mapping
from consensus_decentralization.mappings.default_mapping import DefaultMapping
from consensus_decentralization.mappings.ethereum_mapping import EthereumMapping
from consensus_decentralization.mappings.cardano_mapping import CardanoMapping
from consensus_decentralization.mappings.tezos_mapping import TezosMapping
from consensus_decentralization.helper import INTERIM_DIR, get_clustering_flag, get_input_directories
from consensus_decentralization.mappings.solana_mapping import SolanaMapping


@pytest.fixture
def setup_and_cleanup():
    """
    This function can be used to set up the right conditions for a test and also clean up after the test is finished.
    The part before the yield command is run before the test (setup) and the part after the yield command is run
    after (cleanup)
    """
    # Set up
    ledger_mapping['sample_bitcoin'] = DefaultMapping
    ledger_parser['sample_bitcoin'] = DefaultParser
    ledger_mapping['sample_ethereum'] = EthereumMapping
    ledger_parser['sample_ethereum'] = EthereumParser
    ledger_mapping['sample_cardano'] = CardanoMapping
    ledger_parser['sample_cardano'] = DummyParser
    ledger_mapping['sample_tezos'] = TezosMapping
    ledger_parser['sample_tezos'] = DummyParser
    ledger_mapping['sample_solana'] = SolanaMapping
    ledger_parser['sample_solana'] = DummyParser
    test_raw_data_dirs = get_input_directories()
    test_output_dir = INTERIM_DIR / "test_output"
    # Create the output directory for each project (as this is typically done in the run.py script before parsing or
    # mapping takes place)
    for project in ['sample_bitcoin', 'sample_ethereum', 'sample_cardano', 'sample_tezos', 'sample_solana']:
        test_project_output_dir = test_output_dir / project
        test_project_output_dir.mkdir(parents=True, exist_ok=True)
    mapping_info_dir = pathlib.Path(__file__).resolve().parent.parent / 'mapping_information'
    # Mock return value of get_clustering_flag
    get_clustering_flag.return_value = True
    yield mapping_info_dir, test_raw_data_dirs, test_output_dir
    # Clean up
    shutil.rmtree(test_output_dir)


@pytest.fixture
def prep_sample_bitcoin_mapping_info():
    mapping_info_dir = pathlib.Path(__file__).resolve().parent.parent / 'mapping_information'
    # Create temp mapping info files for sample project
    shutil.copy2(str(mapping_info_dir / 'addresses/bitcoin.json'),
                 str(mapping_info_dir / 'addresses/sample_bitcoin.json'))
    shutil.copy2(str(mapping_info_dir / 'identifiers/bitcoin.json'),
                 str(mapping_info_dir / 'identifiers/sample_bitcoin.json'))
    yield
    # Remove temp mapping info files
    os.remove(str(mapping_info_dir / 'addresses/sample_bitcoin.json'))
    os.remove(str(mapping_info_dir / 'identifiers/sample_bitcoin.json'))


@pytest.fixture
def prep_sample_ethereum_mapping_info():
    mapping_info_dir = pathlib.Path(__file__).resolve().parent.parent / 'mapping_information'
    # Create temp mapping info files for sample project
    shutil.copy2(mapping_info_dir / 'addresses/ethereum.json', mapping_info_dir / 'addresses/sample_ethereum.json')
    shutil.copy2(mapping_info_dir / 'identifiers/ethereum.json', mapping_info_dir / 'identifiers/sample_ethereum.json')
    yield
    # Remove temp mapping info files
    os.remove(mapping_info_dir / 'addresses/sample_ethereum.json')
    os.remove(mapping_info_dir / 'identifiers/sample_ethereum.json')


@pytest.fixture
def prep_sample_cardano_mapping_info():
    mapping_info_dir = pathlib.Path(__file__).resolve().parent.parent / 'mapping_information'
    # Create temp mapping info files for sample project
    shutil.copy2(mapping_info_dir / 'clusters/cardano.json', mapping_info_dir / 'clusters/sample_cardano.json')
    shutil.copy2(mapping_info_dir / 'identifiers/cardano.json', mapping_info_dir / 'identifiers/sample_cardano.json')
    yield
    # Remove temp mapping info files
    os.remove(mapping_info_dir / 'clusters/sample_cardano.json')
    os.remove(mapping_info_dir / 'identifiers/sample_cardano.json')


@pytest.fixture
def prep_sample_tezos_mapping_info():
    mapping_info_dir = pathlib.Path(__file__).resolve().parent.parent / 'mapping_information'
    # Create temp mapping info files for sample project
    shutil.copy2(mapping_info_dir / 'addresses/tezos.json', mapping_info_dir / 'addresses/sample_tezos.json')
    yield
    # Remove temp mapping info files
    os.remove(str(mapping_info_dir / 'addresses/sample_tezos.json'))


@pytest.fixture
def prep_sample_solana_mapping_info():
    mapping_info_dir = pathlib.Path(__file__).resolve().parent.parent / 'mapping_information'
    # Create temp mapping info files for sample project
    shutil.copy2(mapping_info_dir / 'identifiers/solana.json', mapping_info_dir / 'identifiers/sample_solana.json')
    yield
    # Remove temp mapping info files
    os.remove(mapping_info_dir / 'identifiers/sample_solana.json')


@pytest.fixture
def prep_sample_solana_cluster_mapping_info():
    mapping_info_dir = pathlib.Path(__file__).resolve().parent.parent / 'mapping_information'
    # Create temp mapping info files for the sample project, INCLUDING clusters, so that
    # the cluster-based mapping (map_from_known_clusters) is exercised.
    shutil.copy2(mapping_info_dir / 'identifiers/solana.json', mapping_info_dir / 'identifiers/sample_solana.json')
    shutil.copy2(mapping_info_dir / 'clusters/solana.json', mapping_info_dir / 'clusters/sample_solana.json')
    yield
    # Remove temp mapping info files
    os.remove(mapping_info_dir / 'identifiers/sample_solana.json')
    os.remove(mapping_info_dir / 'clusters/sample_solana.json')


def test_map(setup_and_cleanup, prep_sample_bitcoin_mapping_info):
    mapping_info_dir, test_raw_data_dirs, test_output_dir = setup_and_cleanup

    parsed_data = parse(ledger='sample_bitcoin', input_dirs=test_raw_data_dirs)
    apply_mapping(project='sample_bitcoin', parsed_data=parsed_data, output_dir=test_output_dir)

    mapped_data_file = test_output_dir / 'sample_bitcoin/mapped_data_clustered.json'
    assert mapped_data_file.is_file()


def test_bitcoin_mapping(setup_and_cleanup, prep_sample_bitcoin_mapping_info):
    mapping_info_dir, test_raw_data_dirs, test_output_dir = setup_and_cleanup
    with open(mapping_info_dir / 'addresses/sample_bitcoin.json') as f:
        pool_addresses = json.load(f)
    pool_addresses['0000000000000000000000000000000000000000'] = {'name': 'TEST2', 'source': ''}
    with open(mapping_info_dir / 'addresses/sample_bitcoin.json', 'w') as f:
        f.write(json.dumps(pool_addresses))

    parsed_data = parse(ledger='sample_bitcoin', input_dirs=test_raw_data_dirs)
    apply_mapping(project='sample_bitcoin', parsed_data=parsed_data, output_dir=test_output_dir)

    expected_block_creators = {
        '507715': 'GBMiners',
        '511342': 'GBMiners',
        '510888': 'BTC.TOP',
        '649064': 'TEST2'
    }
    expected_mapping_methods = {
        '507715': 'known_identifiers',
        '511342': 'known_identifiers',
        '510888': 'known_identifiers',
        '649064': 'known_addresses'
    }
    with open(test_output_dir / 'sample_bitcoin/mapped_data_clustered.json') as f:
        mapped_data = json.load(f)
    for block in mapped_data:
        if block['number'] in expected_block_creators:
            assert block['creator'] == expected_block_creators[block['number']]
            assert block['mapping_method'] == expected_mapping_methods[block['number']]


def test_ethereum_mapping(setup_and_cleanup, prep_sample_ethereum_mapping_info):
    mapping_info_dir, test_raw_data_dirs, test_output_dir = setup_and_cleanup

    with open(mapping_info_dir / 'addresses/sample_ethereum.json') as f:
        addresses = json.load(f)
    addresses['0xe9b54a47e3f401d37798fc4e22f14b78475c2afc'] = {'name': 'TEST2', 'source': ''}
    with open(mapping_info_dir / 'addresses/sample_ethereum.json', 'w') as f:
        f.write(json.dumps(addresses))

    parsed_data = parse(ledger='sample_ethereum', input_dirs=test_raw_data_dirs)
    apply_mapping(project='sample_ethereum', parsed_data=parsed_data, output_dir=test_output_dir)

    expected_block_creators = {
        '16382083': 'MEV Builder: 0x3B...436',
        '11184490': '0x45133a7e1cc7e18555ae8a4ee632a8a61de90df6',
        '11183702': 'TEST2',
        '11183793': 'ezil.me'
    }
    expected_mapping_methods = {
        '16382083': 'known_addresses',
        '11184490': 'fallback_mapping',
        '11183702': 'known_addresses',
        '11183793': 'known_identifiers'
    }

    with open(test_output_dir / 'sample_ethereum/mapped_data_clustered.json') as f:
        mapped_data = json.load(f)
    for block in mapped_data:
        if block['number'] in expected_block_creators:
            assert block['creator'] == expected_block_creators[block['number']]
            assert block['mapping_method'] == expected_mapping_methods[block['number']]


def test_cardano_mapping(setup_and_cleanup, prep_sample_cardano_mapping_info):
    mapping_info_dir, test_raw_data_dirs, test_output_dir = setup_and_cleanup

    parsed_data = parse(ledger='sample_cardano', input_dirs=test_raw_data_dirs)
    apply_mapping(project='sample_cardano', parsed_data=parsed_data, output_dir=test_output_dir)

    expected_block_creators = {
        '17809932': 'Cashflow',
        '66666666666': '1 Percent Pool',
        '00000000001': 'Input Output (iohk.io)'
    }
    expected_mapping_methods = {
        '17809932': 'known_clusters',
        '66666666666': 'known_clusters',
        '00000000001': 'known_addresses'
    }
    with open(test_output_dir / 'sample_cardano/mapped_data_clustered.json') as f:
        mapped_data = json.load(f)
    for block in mapped_data:
        if block['number'] in expected_block_creators:
            assert block['creator'] == expected_block_creators[block['number']]
            assert block['mapping_method'] == expected_mapping_methods[block['number']]


def test_tezos_mapping(setup_and_cleanup, prep_sample_tezos_mapping_info):
    mapping_info_dir, test_raw_data_dirs, test_output_dir = setup_and_cleanup

    parsed_data = parse(ledger='sample_tezos', input_dirs=test_raw_data_dirs)
    apply_mapping(project='sample_tezos', parsed_data=parsed_data, output_dir=test_output_dir)

    expected_block_creators = {
        '1649812': 'Tezos Seoul',
        '1650474': 'TzNode',
        '1651794': '----- UNDEFINED BLOCK PRODUCER -----',
        '0000000': 'tz0000000000000000000000000000000000'
    }
    expected_mapping_methods = {
        '1649812': 'known_addresses',
        '1650474': 'known_addresses',
        '1651794': 'fallback_mapping',
        '0000000': 'fallback_mapping'
    }
    with open(test_output_dir / 'sample_tezos/mapped_data_clustered.json') as f:
        mapped_data = json.load(f)
    for block in mapped_data:
        if block['number'] in expected_block_creators:
            assert block['creator'] == expected_block_creators[block['number']]
            assert block['mapping_method'] == expected_mapping_methods[block['number']]


def test_get_reward_addresses():
    default_mapping = DefaultMapping("sample_bitcoin", output_dir=pathlib.Path(), data_to_map=None)

    block = {
        "number": 625113,
        "timestamp": "2020-04-09 10:48:38+00:00",
        "identifiers": "b'\\x03\\xd9\\x89\\t\\x04\\x89\\xfd\\x8e^/poolin.com/\\xfa\\xbemmL\\xd6\\xe82[\\xc7}\\x07\\x89\\xe5\\xbf.\\xdb\\xed\\xac\\xfd\\xff\\xe6\\xff\\x8a\\t\\xccQ\\xb8\\x11\\x97\\xea\\xae\\t\\xea\\xd3_\\x01\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\xb1\\xe3t\\xf7\\xaf\\xa4\\xcf\\x81\\x8c&\\xdf\\xd6s9\\x19o\\x12\\xf3t\\x1b`\\x00\\xbb\\x0bC\\x00\\xff\\xff\\xff\\xff'",
        "reward_addresses": "3HqH1qGAqNWPpbrvyGjnRxNEjcUKD4e6ea"
    }
    reward_addresses = default_mapping.get_reward_addresses(block)
    assert reward_addresses == ['3HqH1qGAqNWPpbrvyGjnRxNEjcUKD4e6ea']

    block = {"number": -1, "timestamp": "2023-08-07 10:34:38+00:00", "identifiers": "b'mined by Lady X'",
             "reward_addresses": "hello1,hello2,hello3"}
    default_mapping.special_addresses.add("hello2")
    reward_addresses = default_mapping.get_reward_addresses(block)
    assert reward_addresses == ["hello1", "hello3"] or reward_addresses == ["hello3", "hello1"]

    block = {
        "number": -2,
        "timestamp": "2023-08-07 17:52:38+00:00",
        "identifiers": "b'mined by Lady X'",
        "reward_addresses": "hello2"
    }
    reward_addresses = default_mapping.get_reward_addresses(block)
    assert reward_addresses == []

    block = {
        "number": -3,
        "timestamp": "2023-08-07 17:53:38+00:00",
        "identifiers": "b'mined by Lady X'",
        "reward_addresses": None
    }
    reward_addresses = default_mapping.get_reward_addresses(block)
    assert reward_addresses is None

    eth_mapping = EthereumMapping("sample_ethereum", output_dir=pathlib.Path(), data_to_map=None)
    block = {
        "number": 6982695,
        "timestamp": "2018-12-31 00:00:12+00:00",
        "reward_addresses": "0x5a0b54d5dc17e0aadc383d2db43b0a0d3e029c4c",
        "identifiers": "sparkpool-eth-cn-hz2"
    }
    reward_addresses = eth_mapping.get_reward_addresses(block)
    assert reward_addresses == ["0x5a0b54d5dc17e0aadc383d2db43b0a0d3e029c4c"]


def test_cardano_map_from_known_addresses():
    cardano_mapping = CardanoMapping(project_name="sample_cardano", output_dir=pathlib.Path(), data_to_map=None)

    block = {
        "number": 92082690,
        "identifiers": "WAV7",
        "timestamp": "2023-05-09 16:16:21",
        "reward_addresses": "e14a650c7a58d229bbb663cb42fffb36d68c2a6cecf0fd7b9c47e399"
    }
    entity = cardano_mapping.map_from_known_addresses(block)
    assert entity is None

    block = {
        "number": -1,
        "identifiers": "bla",
        "timestamp": "2023-08-10 16:16:21",
        "reward_addresses": ""
    }
    entity = cardano_mapping.map_from_known_addresses(block)
    assert entity == "Input Output (iohk.io)"

    cardano_mapping.special_addresses.add('very special address')
    block = {
        "number": -2,
        "identifiers": "spcl",
        "timestamp": "2023-08-10 17:16:21",
        "reward_addresses": "very special address"
    }
    entity = cardano_mapping.map_from_known_addresses(block)
    assert entity == "----- SPECIAL ADDRESS -----"


def test_solana_mapping(setup_and_cleanup, prep_sample_solana_mapping_info):
    mapping_info_dir, test_raw_data_dirs, test_output_dir = setup_and_cleanup

    parsed_data = parse(ledger='sample_solana', input_dirs=test_raw_data_dirs)
    apply_mapping(project='sample_solana', parsed_data=parsed_data, output_dir=test_output_dir)

    expected_block_creators = {
        '437783806': 'Temporal Emerald',
        '437783795': 'binance staking',
        '437783783': 'Coinbase 05',
        '437783803': 'EvnRmnMrd69kFdbLMxWkTn1icZ7DCceRhvmb2SJXqDo4',
        '437783799': 'DP9SwUE9Wi4NijWxgKDmmVsqGtQ597AKKmDBwzpt8GgZ',
    }
    expected_mapping_methods = {
        '437783806': 'known_identifiers',
        '437783795': 'known_identifiers',
        '437783783': 'known_identifiers',
        '437783803': 'fallback_mapping',
        '437783799': 'fallback_mapping',
    }
    with open(test_output_dir / 'sample_solana/mapped_data_clustered.json') as f:
        mapped_data = json.load(f)
    for block in mapped_data:
        if block['number'] in expected_block_creators:
            assert block['creator'] == expected_block_creators[block['number']]
            assert block['mapping_method'] == expected_mapping_methods[block['number']]


def test_solana_cluster_mapping(setup_and_cleanup, prep_sample_solana_cluster_mapping_info):
    """
    With a clusters/solana.json present, blocks whose vote account (the block's identifier)
    belongs to a cluster must be mapped to the cluster name via map_from_known_clusters,
    overriding the per-validator identifier mapping. Blocks whose vote account is not in the
    clusters file are left to the earlier mapping methods (here: fallback), which exercises
    the None branch of the override.
    """
    mapping_info_dir, test_raw_data_dirs, test_output_dir = setup_and_cleanup

    parsed_data = parse(ledger='sample_solana', input_dirs=test_raw_data_dirs)
    apply_mapping(project='sample_solana', parsed_data=parsed_data, output_dir=test_output_dir)

    # Haz7...  = "Temporal Emerald"  -> multi-member cluster "Temporal"
    # ERut...  = "Coinbase 05"       -> multi-member cluster "Coinbase"
    # 3N7s...  = "binance staking"   -> singleton, cluster name "Binance Staking"
    expected_block_creators = {
        '437783806': 'Temporal',
        '437783795': 'Binance Staking',
        '437783783': 'Coinbase',
    }
    expected_mapping_methods = {
        '437783806': 'known_clusters',
        '437783795': 'known_clusters',
        '437783783': 'known_clusters',
        # Not in the clusters file -> cluster lookup returns None -> fallback stands.
        '437783803': 'fallback_mapping',
        '437783799': 'fallback_mapping',
    }
    with open(test_output_dir / 'sample_solana/mapped_data_clustered.json') as f:
        mapped_data = json.load(f)
    for block in mapped_data:
        if block['number'] in expected_mapping_methods:
            assert block['mapping_method'] == expected_mapping_methods[block['number']]
        if block['number'] in expected_block_creators:
            assert block['creator'] == expected_block_creators[block['number']]
