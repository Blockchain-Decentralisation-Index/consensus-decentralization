"""
Module with helper functions
"""
import csv
import pathlib
import json
import datetime
import calendar
import argparse
import logging
from functools import lru_cache
from collections import defaultdict

import requests
from yaml import safe_load

ROOT_DIR = pathlib.Path(__file__).resolve().parent.parent
INTERIM_DIR = ROOT_DIR / 'processed_data'
MAPPING_INFO_DIR = ROOT_DIR / 'mapping_information'
RESULTS_DIR = ROOT_DIR / 'results'
IPFS_CACHE_DIR = ROOT_DIR / '.ipfs_cache'

with open(ROOT_DIR / "config.yaml") as f:
    config = safe_load(f)


def valid_date(date_string):
    """
    Validates the given string if it corresponds to a correct date and is in YYYY-MM-DD, YYYY-MM or YYYY format
    :param date_string: a string representation of a date
    :returns: the string as it was given, if it corresponds to a valid date in the specified format
    :raises argparse.ArgumentTypeError: if the wrong format is used or if the date_string doesn't correspond to a valid
    date
    """
    try:
        get_timeframe_beginning(date_string)
    except ValueError:
        raise argparse.ArgumentTypeError("Please use the format YYYY-MM-DD for the timeframe argument "
                                         "(day and month can be omitted).")
    return date_string


def get_timeframe_beginning(timeframe):
    """
    Determines the first day of a given timeframe
    :param timeframe: a string representation of the timeframe in YYYY-MM-DD, YYYY-MM or YYYY format
    :returns: a date object corresponding to the first day of the timeframe
    """
    return datetime.date.fromisoformat(timeframe.ljust(10, 'x').replace('xxx', '-01'))


def get_timeframe_end(timeframe):
    """
    Determines the last day of a given timeframe
    :param timeframe: a string representation of the timeframe in YYYY-MM-DD, YYYY-MM or YYYY format
    :returns: a date object corresponding to the last day of the timeframe
    """
    timeframe_with_month = timeframe.ljust(7, 'x').replace('xxx', '-12')
    year, month = [int(i) for i in timeframe_with_month.split('-')][:2]
    days_in_month = calendar.monthrange(year, month)[1]
    timeframe_with_day = timeframe_with_month.ljust(10, 'x').replace('xxx', f'-{days_in_month}')
    return datetime.date.fromisoformat(timeframe_with_day)


def get_time_period(frm, to):
    """
    Determines the first day and last day of a time period defined by frm and to
    :param frm: a string representation of the starting date in YYYY-MM-DD, YYYY-MM or YYYY format, or the empty string
    :param to: a string representation of the end date plus one day in YYYY-MM-DD, YYYY-MM or YYYY format, or the empty
    string
    :returns: a tuple of date objects with the first and last day of the time period
    """
    start = get_timeframe_beginning(frm) if frm else datetime.date.min
    end = get_timeframe_beginning(to) - datetime.timedelta(1) if to else datetime.date.max
    return start, end


def get_pool_identifiers(project_name):
    """
    Retrieves identifiers (tags, etc) about the pools of a project.
    :param project_name: string that corresponds to the project under consideration
    :returns: a dictionary where each key corresponds to an identifier (tag, ticker, etc) and each value is
    another dictionary with information about the entity behind the identifier (name of the pool, website, etc),
    or an empty dictionary if no information is available for the project (the relevant file does not exist)
    """
    try:
        with open(MAPPING_INFO_DIR / f'identifiers/{project_name}.json', encoding='utf-8') as f:
            identifiers = json.load(f)
    except FileNotFoundError:
        return dict()

    return identifiers


def get_pool_clusters(project_name):
    """
    Retrieves data regarding the clusters of pools of a project.
    :param project_name: string that corresponds to the project under consideration
    :returns: a dictionary where each key corresponds to a unique pool id (e.g. pool hash) and each value is a
    dictionary of the form: {'cluster': <name of the cluster>, 'pool': <name of the pool>, 'source': <source>},
    or an empty dictionary if no information is available for the project (the relevant file does not exist)
    """
    try:
        with open(MAPPING_INFO_DIR / f'clusters/{project_name}.json') as f:
            clusters = json.load(f)
    except FileNotFoundError:
        return dict()
    return clusters


@lru_cache(maxsize=2)
def get_pool_legal_links(timeframe):
    """
    Retrieves data regarding the links between the pools of a project.
    Caches the result for quick access when the function is called again with the same arguments.
    :param timeframe: string that corresponds to the timeframe under consideration (in YYYY-MM-DD, YYYY-MM or YYYY
    format)
    :returns: a dictionary that reveals the ownership of pools
    """
    start = get_timeframe_beginning(timeframe)
    end = get_timeframe_end(timeframe)

    legal_links = {}

    with open(MAPPING_INFO_DIR / 'legal_links.json') as f:
        legal_data = json.load(f)

    for cluster_name, pools in legal_data.items():
        for pool_info in pools:
            link_start, link_end = get_time_period(pool_info['from'], pool_info['to'])

            check_list = [  # Check if two periods overlap at any point
                start <= link_start <= end,
                start <= link_end <= end,
                link_start <= start <= link_end,
                link_start <= end <= link_end
            ]
            if any(check_list):
                legal_links[pool_info['name']] = cluster_name

    for parent, child in legal_links.items():  # resolve chain links
        while child in legal_links.keys():
            next_child = legal_links[child]
            if next_child == child:
                # Cluster's name is the same as the primary pool's name
                break
            elif next_child == parent:
                raise AssertionError(f'Circular dependency: {parent}, {child}')
            else:
                child = next_child
        legal_links[parent] = child

    return legal_links


def get_known_addresses(project_name):
    """
    Retrieves the addresses associated with pools of a certain project over a given timeframe
    :param project_name: string that corresponds to the project under consideration
    :returns: a dictionary with known addresses and the names of the pools that own them (given that the timeframe of
    the ownership overlaps with the timeframe under consideration), or an empty dictionary if no addresses are known
    for the project (no such file exists)
    """
    try:
        with open(MAPPING_INFO_DIR / f'addresses/{project_name}.json') as f:
            address_data = json.load(f)
    except FileNotFoundError:
        return dict()

    return {address: addr_info['name'] for address, addr_info in address_data.items()}


def write_blocks_per_entity_to_file(output_dir, blocks_per_entity, dates, filename):
    """
    Produces a csv file with information about the resources (blocks) that each entity controlled over some timeframe.
    The entries are sorted so that the entities that controlled the most resources appear first.
    :param output_dir: pathlib.PosixPath object of the output directory where the produced csv file is written to.
    :param blocks_per_entity: a dictionary with entities as keys and lists as values, where each list represents the
        number of blocks produced by the entity in each time chunk
    :param dates: a list of strings, each representing a chunk of time that was analyzed
    :param filename: the name to be given to the produced file.
    """
    with open(output_dir / filename, 'w', newline='') as f:
        csv_writer = csv.writer(f)
        csv_writer.writerow(['Entity \\ Date'] + dates)  # write header
        for entity, blocks_per_chunk in blocks_per_entity.items():
            entity_row = [entity]
            for date in dates:
                try:
                    entity_row.append(blocks_per_chunk[date])
                except KeyError:
                    entity_row.append(0)
            csv_writer.writerow(entity_row)


def get_blocks_per_entity_from_file(filepath, population_windows):
    """
    Retrieves information about the number of blocks that each entity produced over some timeframe for some project.
    :param filepath: the path to the file with the relevant information. It can be either an absolute or a relative
    path in either a pathlib.PosixPath object or a string.
    :param population_windows: int representing the number of windows to look back and forward when determining if an
    entity is active during a certain time frame
    :returns: a tuple of length 2 where the first item is a list of time chunks (strings) and the second item is a
    dictionary with entities (keys) and a list of the number of blocks they produced during each time chunk (values)
    """
    blocks_per_entity = defaultdict(dict)
    with open(filepath, newline='') as f:
        csv_reader = csv.reader(f)
        header = next(csv_reader, None)
        dates = header[1:]
        for row in csv_reader:
            entity = row[0]
            for idx, item in enumerate(row[1:]):
                if item == '0':
                    if population_windows == 'all':
                        blocks_per_entity[entity][dates[idx]] = 0
                    else:
                        # If the entity hasn't produced any blocks in the current time chunk, we only consider it as
                        # active if it has produced at least one block in population_windows time chunks before or after
                        # (otherwise it's not considered part of the population for this time frame)
                        for i in range(max(0, idx - population_windows), min(len(row) - 1, idx + population_windows + 1)):
                            if row[i + 1] != '0':
                                blocks_per_entity[entity][dates[idx]] = 0
                else:
                    blocks_per_entity[entity][dates[idx]] = int(item)
    return dates, blocks_per_entity


def get_special_addresses(project_name):
    """
    Retrieves special addresses of a project, such as treasury addresses, protocol related smart contracts, etc.
    :param project_name: string that corresponds to the project under consideration
    :returns: a set of addresses or an empty set if no special addresses are found for the project
    """
    with open(MAPPING_INFO_DIR / 'special_addresses.json') as f:
        special_address_data = json.load(f)

    try:
        special_addresses = special_address_data[project_name]
    except KeyError:
        return set()

    return set([addr['address'] for addr in special_addresses])


def get_config_data():
    """
    Reads the configuration data of the project. This data is read from a file named "confing.yaml" located at the
    root directory of the project.
    :returns: a dictionary of configuration keys and values
    """
    return config


def get_metrics_config():
    """
    Reads data about the metrics that will be used from the project's config file. All metrics that are mentioned in
    the file (not in comments) will be used at the "analyze" and "plot" stages. If a metric is parameterized, then the
    values of its parameters are also given in this file. To add a new metric, one can add a new entry in the file, and
    to disable a metric it suffices to comment out the relevant line(s).
    :returns: a dictionary where the keys correspond to metric names and the values to their configurations
    (dictionary of parameter - value pairs for each parameter that the metric takes)
    :raises AssertionError if the file defines different parameter values for metrics that are supposed to be
    consistent (e.g. entropy and entropy percentage)
    """
    config = get_config_data()
    metrics = config['metrics']
    metric_families = [['entropy', 'entropy_percentage']]
    for metric_family in metric_families:
        # ensure that parameter values that correspond to the same family of metrics are consistent
        params = None
        for metric in metric_family:
            if metric in metrics:
                if params is None:
                    params = metrics[metric]
                else:
                    assert metrics[metric] == params, "Metrics that belong in the same family (e.g. entropy and entropy " \
                                                      "percentage) must use the same parameter values. " \
                                                      "Please update your config.yaml file accordingly."
    return metrics


def get_ledgers():
    """
    Retrieves data regarding the ledgers to use
    :returns: a list of strings that correspond to the ledgers that will be used (unless overriden by the relevant cmd
    arg)
    """
    config = get_config_data()
    ledgers = config['ledgers']
    return ledgers


def get_start_end_dates():
    """
    Retrieves the start and end dates for which to analyze data
    :returns: a tuple of two strings, (<start date>, <end date>)
    """
    config = get_config_data()
    for date_type in ['start', 'end']:
        if not valid_date(str(config['timeframe'][f'{date_type}_date'])):
            raise ValueError(f'Invalid {date_type} date')
    return str(config['timeframe']['start_date']), str(config['timeframe']['end_date'])


def read_mapped_project_data(project_dir):
    """
    Reads the mapped data from a project's output directory
    :param project_dir: pathlib.PosixPath object of the output directory corresponding to the project
    :returns: a dictionary with the mapped data
    """
    with open(project_dir / get_mapped_data_filename(get_clustering_flag())) as f:
        data = json.load(f)
    return data


def get_representative_dates(time_chunks):
    """
    Formats the time chunks into strings that can be used in the output files or as labels in plots
    :param time_chunks: list of tuples of (start_date, end_date) where each date is a datetime.date object
    :returns: a list of strings that represent each time chunk. Specifically, the middle date of each chunk is used as
        the representative date.
    """
    return [str(chunk[0] + (chunk[1] - chunk[0]) // 2) for chunk in time_chunks]


def get_aggregated_data_dir_name(clustering_flag):
    """
    Determines the name of the directory that will contain the aggregated data
    :param clustering_flag: boolean that determines whether the data is clustered or not
    :returns: str that corresponds to the name of the directory
    """
    return 'blocks_per_entity_' + ('clustered' if clustering_flag else 'non_clustered')


def get_blocks_per_entity_filename(timeframe, estimation_window, frequency):
    """
    Determines the filename of the csv file that contains the aggregated data
    :param timeframe: tuple of (start_date, end_date) where each date is a datetime.date object
    :param estimation_window: int that represents the number of days to use for the estimation window, or None,
        which means that the whole timeframe should be used for each estimation
    :param frequency: int that represents how frequently to sample the data, in days, or None, which means that only
        one time point will be considered (snapshot instead of longitudinal data)
    :returns: str that corresponds to the filename of the csv file
    """
    if estimation_window is None and frequency is None:
        return f'all_from_{timeframe[0]}_to_{timeframe[1]}.csv'
    return f'{estimation_window}_day_window_from_{timeframe[0]}_to_{timeframe[1]}_sampled_every_{frequency}_days.csv'


def get_date_from_block(block, level='day'):
    """
    Gets the date from the timestamp of a block.
    :param block: dictionary of block data
    :param level: string, one of: year, month, day (default: day)
    :returns: a string that corresponds to the date of the block at the given level
    :raises ValueError: if the level is not one of: year, month, day
    """
    timestamp = block['timestamp']
    if level == 'year':
        return timestamp[:4]
    elif level == 'month':
        return timestamp[:7]
    elif level == 'day':
        return timestamp[:10]
    raise ValueError(f'Invalid level: {level}')


def get_estimation_window_and_frequency():
    """
    Retrieves the estimation window and frequency to be used in the analysis
    :returns: tuple of (int, int) or (None, None), with the first item representing the number of days to use for the
    estimation window and the second item representing how frequently to sample the data, in days
    :raises ValueError: if the estimation_window or frequency field is missing from the config file
                        or if one of them is set to None while the other is not
    """
    try:
        config = get_config_data()
        estimation_window = config['estimation_window']
        frequency = config['frequency']
        if estimation_window is None and frequency is None:
            return None, None
        if estimation_window is None or frequency is None:
            raise ValueError('Both "estimation_window" and "frequency" should be either set to some number or empty')
        return estimation_window, frequency
    except KeyError:
        raise ValueError('"estimation_window" or "frequency" missing from config file')


def get_population_windows():
    """
    Retrieves the number of windows to be used for estimating the population of block producers
    :returns: int representing the number of windows to look back and forward when determining if an entity is active
    during a certain time frame
    :raises ValueError: if the population_windows field is missing from the config file
    """
    try:
        config = get_config_data()
        population_windows = config['population_windows']
        return population_windows
    except KeyError:
        raise ValueError('"population_windows" missing from config file')


def get_plot_flag():
    """
    Gets the flag that determines whether generate plots for the output
    :returns: boolean
    :raises ValueError: if the flag is not set in the config file
    """
    config = get_config_data()
    try:
        return config['plot_parameters']['plot']
    except KeyError:
        raise ValueError('Flag "plot" missing from config file')


def get_plot_config_data():
    """
    Retrieves the plot-related config parameters
    :returns: dictionary
    """
    return get_config_data()['plot_parameters']


def get_force_map_flag():
    """
    Gets the flag that determines whether to forcefully map the data
    :returns: boolean
    :raises ValueError: if the flag is not set in the config file
    """
    config = get_config_data()
    try:
        return config['force_map']
    except KeyError:
        raise ValueError('Flag "force_map" missing from config file')


def get_clustering_flag():
    """
    Gets the flag that determines whether to perform clustering
    :returns: boolean
    :raises ValueError: if the flag is not set in the config file
    """
    config = get_config_data()
    try:
        return config['clustering']
    except KeyError:
        raise ValueError('Flag "clustering" missing from config file')


def get_results_dir(estimation_window, frequency, population_windows):
    """
    Retrieves the path to the results directory for the specific config parameters
    :returns: pathlib.PosixPath object
    """
    results_dir_name = (f'{estimation_window}_day_window_with_{population_windows}_population_windows_sampled_every'
                        f'_{frequency}_days')
    return RESULTS_DIR / results_dir_name


def get_mapped_data_filename(clustering_flag):
    """
    Retrieves the filename of the mapped data file
    :param clustering_flag: boolean that determines whether the data is clustered or not
    :returns: str
    """
    return 'mapped_data_' + ('clustered' if clustering_flag else 'non_clustered') + '.json'


def get_output_filename(clustering_flag):
    """
    Retrieves the filename of the output file
    :param clustering_flag: boolean that determines whether clustering was performed
    :returns: str with the filename of the output file, which depends on whether clustering was performed
    """
    return 'output_' + ('clustered' if clustering_flag else 'non_clustered') + '.csv'


def get_ipfs_gateways():
    """
    Retrieves the IPFS gateway URLs used to resolve `ipfs://<CID>` entries in input_directories. If more than one is
    configured, they are tried in order for each file, falling back to the next one on failure (e.g. a public
    gateway followed by a local node's gateway, typically http://127.0.0.1:8080).
    :returns: list of str, the base URLs of the gateways (defaults to a single public gateway if not set in the
        config file)
    """
    config = get_config_data()
    gateways = config.get('ipfs_gateway', 'https://ipfs.io')
    if isinstance(gateways, str):
        gateways = [gateways]
    return [gateway.rstrip('/') for gateway in gateways]


def fetch_ipfs_directory(cid, subpath=''):
    """
    Fetches the raw data files (one per ledger defined in the config file) from an IPFS directory, via the configured
    IPFS gateway(s), and caches them locally. Files that have already been cached are not re-fetched. If a file can't
    be fetched from any configured gateway, it is skipped (a warning is logged), so that other input directories may
    still be used to look for the corresponding ledger's raw data.
    :param cid: string, the IPFS CID of a (unixfs) directory that is expected to contain files named
        <ledger>_raw_data.json for one or more ledgers
    :param subpath: string, an optional path within the directory pointed to by the CID
    :returns: pathlib.PosixPath object of the local directory where the fetched files are cached
    """
    gateways = get_ipfs_gateways()
    cache_dir = IPFS_CACHE_DIR / cid / subpath if subpath else IPFS_CACHE_DIR / cid
    cache_dir.mkdir(parents=True, exist_ok=True)
    gateway_path = f'{cid}/{subpath}' if subpath else cid

    for ledger in get_ledgers():
        filename = f'{ledger}_raw_data.json'
        local_path = cache_dir / filename
        if local_path.is_file():
            continue
        for gateway in gateways:
            url = f'{gateway}/ipfs/{gateway_path}/{filename}'
            try:
                response = requests.get(url, timeout=60)
                response.raise_for_status()
            except requests.RequestException as e:
                logging.warning(f'Could not fetch {filename} from IPFS at {url}: {e}')
                continue
            local_path.write_bytes(response.content)
            break

    return cache_dir


def get_input_directories():
    """
    Reads the config file and retrieves the directories to look for raw block data. Entries can be local paths,
    relative to the root directory of the repository, or IPFS references of the form `ipfs://<CID>` (optionally
    `ipfs://<CID>/<subpath>`), in which case the relevant raw data files are fetched (if not already cached) from the
    configured IPFS gateway and the local cache directory is used in their place.
    :returns: a list of directories that may contain the raw block data
    """
    config = get_config_data()
    input_dirs = []
    for entry in config['input_directories']:
        entry = str(entry)
        if entry.startswith('ipfs://'):
            cid, _, subpath = entry[len('ipfs://'):].partition('/')
            input_dirs.append(fetch_ipfs_directory(cid, subpath))
        else:
            input_dirs.append(ROOT_DIR / entry)
    return input_dirs
