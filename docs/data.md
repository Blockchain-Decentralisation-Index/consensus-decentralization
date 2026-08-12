# Data collection

Currently, the data for the analysis of the different ledgers is collected through 
[Google BigQuery](https://console.cloud.google.com/bigquery) .

Note that when saving results from BigQuery you should select the option "JSONL (newline delimited)".

## Sample data & queries

Sample data for all blockchains can be found [here](https://uoe-my.sharepoint.com/:f:/g/personal/s2125265_ed_ac_uk/Eg0L2n9P-txOtibKu9CXfloBt6_D-3D1AEsS2evtXIatVA?e=qHhFp4).
Alternatively, one can retrieve the data directly from BigQuery using the queries below.

### Bitcoin

```
SELECT block_number as number, block_timestamp as timestamp, coinbase_param as identifiers, `bigquery-public-data.crypto_bitcoin.transactions`.outputs
FROM `bigquery-public-data.crypto_bitcoin.transactions`
JOIN `bigquery-public-data.crypto_bitcoin.blocks` ON `bigquery-public-data.crypto_bitcoin.transactions`.block_number = `bigquery-public-data.crypto_bitcoin.blocks`.number
WHERE is_coinbase is TRUE
AND timestamp > '2018-01-01'
ORDER BY timestamp
```

### Bitcoin Cash

```
SELECT block_number as number, block_timestamp as timestamp, coinbase_param as identifiers, `bigquery-public-data.crypto_bitcoin_cash.transactions`.outputs
FROM `bigquery-public-data.crypto_bitcoin_cash.transactions`
JOIN `bigquery-public-data.crypto_bitcoin_cash.blocks` ON `bigquery-public-data.crypto_bitcoin_cash.transactions`.block_number = `bigquery-public-data.crypto_bitcoin_cash.blocks`.number
WHERE is_coinbase is TRUE
AND timestamp > '2018-01-01'
ORDER BY timestamp
```

### Cardano

```
SELECT `iog-data-analytics.cardano_mainnet.block`.slot_no as number, `iog-data-analytics.cardano_mainnet.pool_offline_data`.ticker_name as identifiers, `iog-data-analytics.cardano_mainnet.block`.block_time as timestamp,`iog-data-analytics.cardano_mainnet.block`.pool_hash as reward_addresses
FROM `iog-data-analytics.cardano_mainnet.block`
LEFT JOIN `iog-data-analytics.cardano_mainnet.pool_offline_data` ON `iog-data-analytics.cardano_mainnet.block`.pool_hash = `iog-data-analytics.cardano_mainnet.pool_offline_data`.pool_hash
WHERE `iog-data-analytics.cardano_mainnet.block`.block_time > '2018-01-01'
ORDER BY `iog-data-analytics.cardano_mainnet.block`.block_time
```

### Dogecoin

```
SELECT block_number as number, block_timestamp as timestamp, coinbase_param as identifiers, `bigquery-public-data.crypto_dogecoin.transactions`.outputs
FROM `bigquery-public-data.crypto_dogecoin.transactions`
JOIN `bigquery-public-data.crypto_dogecoin.blocks` ON `bigquery-public-data.crypto_dogecoin.transactions`.block_number = `bigquery-public-data.crypto_dogecoin.blocks`.number
WHERE is_coinbase is TRUE
AND timestamp > '2018-01-01'
ORDER BY timestamp
```

### Ethereum

```
SELECT number, timestamp, miner as reward_addresses, extra_data as identifiers
FROM `bigquery-public-data.crypto_ethereum.blocks`
WHERE timestamp > '2018-01-01'
ORDER BY timestamp
```

### Litecoin

```
SELECT block_number as number, block_timestamp as timestamp, coinbase_param as identifiers, `bigquery-public-data.crypto_litecoin.transactions`.outputs
FROM `bigquery-public-data.crypto_litecoin.transactions`
JOIN `bigquery-public-data.crypto_litecoin.blocks` ON `bigquery-public-data.crypto_litecoin.transactions`.block_number = `bigquery-public-data.crypto_litecoin.blocks`.number
WHERE is_coinbase is TRUE
AND timestamp > '2018-01-01'
ORDER BY timestamp
```

### Tezos

```
SELECT level as number, timestamp, baker as reward_addresses
FROM `public-data-finance.crypto_tezos.blocks`
WHERE timestamp > '2018-01-01'
ORDER BY timestamp
```

### Zcash

```
SELECT block_number as number, block_timestamp as timestamp, coinbase_param as identifiers, `bigquery-public-data.crypto_zcash.transactions`.outputs
FROM `bigquery-public-data.crypto_zcash.transactions`
JOIN `bigquery-public-data.crypto_zcash.blocks` ON `bigquery-public-data.crypto_zcash.transactions`.block_number = `bigquery-public-data.crypto_zcash.blocks`.number
WHERE is_coinbase is TRUE
AND timestamp > '2018-01-01'
ORDER BY timestamp
```

## Automating the data collection process

Instead of executing each of these queries separately on the BigQuery console and saving the results manually, it is
also possible to automate the process using a
[script](https://github.com/Blockchain-Technology-Lab/consensus-decentralization/blob/main/data_collection_scripts/collect_block_data.py)
and collect all relevant data in one go. Executing this script will run queries
from [this file](https://github.com/Blockchain-Technology-Lab/consensus-decentralization/blob/main/data_collection_scripts/queries.yaml).

IMPORTANT: the script uses service account credentials for authentication, therefore before running it, you need to
generate the relevant credentials from Google, as described 
[here](https://developers.google.com/workspace/guides/create-credentials#service-account) and save your key in the
`data_collection_scripts` directory of the project under the name 'google-service-account-key.json'. There is a
[sample file](https://github.com/Blockchain-Technology-Lab/consensus-decentralization/blob/main/data_collection_scripts/google-service-account-key-SAMPLE.json) 
that you can consult, which shows what your credentials are supposed to look like (but note that this is for
informational purposes only, this file is not used in the code).

Once you have set up the credentials, you can just run the following command from the root
directory to retrieve data for all supported blockchains:

`python -m data_collection_scripts.collect_block_data`

There are also two command line arguments that can be used to customize the data collection process:

- `ledgers` accepts any number of the supported ledgers (case-insensitive). For example, adding `--ledgers bitcoin`
  results in collecting data only for Bitcoin, while `--ledgers Bitcoin Ethereum Cardano` would collect data for
  Bitcoin, Ethereum and Cardano. If the `ledgers` argument is omitted, then the default value is used, which 
  is taken from the
  [configuration file](https://github.com/Blockchain-Technology-Lab/consensus-decentralization/blob/main/config.yaml)
  and typically corresponds to all supported blockchains.
- `--force-query` forces the collection of all raw data files, even if the corresponding files already
  exist. By default, this flag is set to False and the script only fetches block data for some blockchain if the
  corresponding file does not already exist.

## Solana

Solana data can be collected in more than one way. This project uses a dedicated
tool ([solana-block-harvester](https://github.com/josephinney/solana-block-harvester))
that reads blocks directly from a Solana RPC node and writes them in the same
NDJSON block format used by the rest of the pipeline. For each block it records
the slot number, the timestamp, the producing validator's vote account (as
`identifiers`) and the validator's identity account (as `reward_addresses`).

The same tool also produces the `identifiers/solana.json` mapping file, keyed by
vote account, with each validator's published `name` and `homepage` sourced from
Solana's on-chain Config program. Only validators that publish metadata are
included, so this file can be reused as a reference across any range of blocks.
Since validators can update their metadata over time, this file should ideally
be regenerated periodically to stay current.

## Reading input data from IPFS

In addition to local directories, entries in the `input_directories` list of the
[configuration file](https://github.com/Blockchain-Technology-Lab/consensus-decentralization/blob/main/config.yaml)
can be IPFS references of the form `ipfs://<CID>` (optionally `ipfs://<CID>/<subpath>`). `<CID>` combined with
`<subpath>` (if given) must resolve directly to a (unixfs) directory that contains raw data files named
`<ledger>_raw_data.json`, in the same format expected in a local input directory (one file per ledger, following the
schemas described above) - not to a parent/wrapper directory that merely contains such a directory.

For example, a dataset publisher might give you a CID whose root only contains a single named subdirectory (e.g.
`solana-dataset/`) which in turn holds the actual `<ledger>_raw_data.json` file. In that case the CID alone is not
enough - you need `ipfs://<CID>/solana-dataset` so that the reference points directly at the directory containing the
`.json` file. You can check a CID's contents beforehand by browsing `https://<gateway>/ipfs/<CID>/` (e.g.
`https://ipfs.io/ipfs/<CID>/`) in a browser.

When such an entry is encountered, the relevant files are fetched from the gateway(s) configured via `ipfs_gateway` in
the configuration file (a public gateway such as `https://ipfs.io` by default) and cached locally under
`.ipfs_cache/` at the root of the repository, so that they are only fetched once. `ipfs_gateway` can also be a list
of gateway URLs, in which case they are tried in order for each file, falling back to the next one on failure -
useful for falling back to a local/self-hosted node's gateway (typically `http://127.0.0.1:8080`, requires running
`ipfs daemon`) if a public gateway is unavailable or rate-limited. Note that the first item of `input_directories` is
used as the destination for newly collected data (see above) and therefore should not be an IPFS reference.
