# Mappings

A mapping is responsible for linking blocks to the entities that created them. 
While the parsed data contains
information about the addresses that received rewards for producing some block
or identifiers that are related to them,
it does not contain information about the entities that control these addresses,
which is where the mapping comes in.

The mapping takes as input the parsed data and outputs a file (`processed_data/<project_name>/mapped_data.json`), 
which is structured as follows:

```
[
    {
        "number": "<block's number>",
        "timestamp": "<block's timestamp of the form: yyyy-mm-dd hh:mm:ss UTC>",
        "reward_addresses": "<address1>,<address2>"
        "creator": <entity that created the block>,
        "mapping_method": <method used to map the block to its creator>
    }
]
```


## Mapping Information

To assist the mapping process, the directory `mapping_information/` contains
mapping information about the supported projects.

There exist three subdirectories and two additional files. In each subdirectory
there exists a file for
the corresponding ledger data, if such data exists.

#### Identifiers

The files under `identifiers` define information about block creators. Each key
corresponds to a tag or ticker, by which the pool is identifiable in its
produced blocks. The value for each key is a dictionary of pool-related
information, specifically its name, a URL to its homepage, etc. Each file's
structure is as follows:
```
{
  "P1": {
      "name": "Pool P1",
      "homepage": "example.com/p1"
  },
  "--P2--": {
      "name": "Pool P2",
      "homepage": "example.com/p2"
  }
}
```

#### Clusters

The files under `clusters` define information about pool clusters.
Each key corresponds to a unique pool id (e.g. pool hash in Cardano, vote account in Solana).
The value for each key is a dictionary including
the cluster to which the pool belongs, the pool's name, and the source of 
information about the cluster. The source field is a list of the signals that
caused the pool to be grouped,
and can contain any combination of the following values:

- "homepage": the pools share the same homepage.
- "ticker": the pools share the same ticker (after stripping trailing digits).
- "name": the pools share the same name (after lowercasing and stripping 
trailing digits).
- "description": the pools share the same description.
- "singleton": the pool could not be grouped with any other pool; the cluster
name is the pool's own name. Singleton entries are included so that all pools
can be looked up by their pool id, even if they are not part of a multi-pool
cluster.


Each file's structure is as follows:
```
{
  "pool id 1": {
      "cluster": "cluster A",
      "pool": "Pool P1",
      "source": ["homepage", "ticker"]
  },
  "pool id 2": {
      "cluster": "cluster B",
      "pool": "--P2--",
      "source": ["singleton"]
  }
}
```

#### Addresses
The files under `addresses` define ownership information about addresses. As
with clusters, for each address the pool ownership information defines the
pool's name and a public source of information about the ownership.
Each file's structure is as follows:
```
{
  "address1": {"name": "Pool P2", "source": "example.com"},
}
```

#### Legal links

The file `legal_links.json` defines legal links between pools and companies,
based on off-chain information.
For example, it defines ownership information of a pool by a company.
The structure of the file is as follows:

```
{
  "<parent company>": [
      {"name": "<pool name>", "from": "<start date>", "to": "<end date>", "source": "<source of information>"}
  ]
}
```

The values for each entry are the same as `clusters` in the above pool
information.

#### Special addresses

The file `special_addresses.json` defines per-project information about
addresses that are not related to some entity but are used for
protocol-specific reasons (e.g. treasury address). 
The format of the file is the following:
```
{
  "Project A": [
      {"address": "A special address 1", "source": "some.public.source"},
      {"address": "A special address 2", "source": "some.public.source"}
  ],
  "Project B": [
      {"address": "B special address", "source": "some.public.source"}
  ]
}
```

## Mapping process implementation

In our implementation, the mapping of a block uses the auxiliary information as
follows.

First, it iterates over all known identifiers and compares each one with the
identifiers of the block.
If a known identifier is a substring of the block's identifier, then a match is
found.

If no identifier match is found, the block's reward addresses are compared
against known pool addresses (including special addresses). If a match is found,
the block is mapped to that pool.

Following, we check if the entity that created the block belongs to a known pool
cluster, and if so, we re-map the block to the cluster.

In all cases, if there is a match, then:

1. We map the block to the matched pool.
2. We associate all of the block's reward addresses (that is, the addresses that receive fees from the block) with 
the matched pool.
3. We record the mapping method that was used to obtain the mapping (`known_identifiers`, `known_addresses` or
`known_clusters`).

If there is a match, we also parse information about pool ownership / legal
links, in order to assign the block to the top level entity, e.g., the pool's
parent company. If a match is found this way, we update
the mapping method to `known_legal_links`.

If all mechanisms fail, the block is assigned to its reward address(es) as a
fallback (mapping_method: fallback_mapping).

## Cardano-specific mapping

Cardano's mapping inherits from the default mapping described above but differs
in the following ways.

**Identifier lookup** is an exact match on the block's pool hash rather than a
substring search, since each Cardano block carries a single unambiguous pool
identifier.

**Address lookup** uses the block's reward address (pool hash) rather than a
general address set. Blocks produced before Cardano's decentralisation event
carry no reward address; these are attributed to
Input Output (IOHK), the entity responsible for producing all blocks during that
period.

**Cluster lookup** is also performed via the reward address (pool hash), which
is used as the key for the clusters file. This means that even pools excluded
from the identifiers file due to ticker
conflicts can still be correctly mapped at the cluster level.

### Cardano pool data preprocessing

The clusters and identifiers files for Cardano are generated automatically from
pool metadata sourced from two places: a BigQuery dataset and a Cardano node
(via db-sync). The two sources are merged on
pool hash, with node data taking priority for fields present in both.

**Identifiers** are keyed by ticker. Tickers used by more than one pool pointing
to a different homepage domain are considered conflicting and excluded, to avoid
false mappings.

**Clusters** are built by scoring every pair of pools and merging those that
score at or above a threshold. Scoring works as follows:

- Same homepage domain: +3
- Same ticker (after stripping trailing digits, e.g. `RAY1` and `RAY2` both
normalise to `RAY`): +2
- Same name (after lowercasing and stripping trailing digits): +2
- Same description: +1
- Both pools have valid but different domains: −1 penalty

The default threshold is 3. A homepage match alone is sufficient signal to
cluster two pools together, but, for example, a ticker match alone is not. 
This is intentional, as tickers are not required to be unique in Cardano,
therefore at least one additional corroborating signal is required.

Transitivity is handled automatically: if A clusters with B and B clusters with
C, all three end up in the same cluster.

## Solana-specific mapping

Solana's mapping inherits from the default mapping described above but differs
in the following ways.

**Identifier lookup** is an exact match on the block's vote account rather than
a substring search, since each Solana block carries a single unambiguous
identifier.

**Address lookup** uses the block's single reward address (the validator's
identity account) rather than a general address set, since each Solana block
has exactly one reward address.

**Cluster lookup** is performed via the block's vote account, which is used as
the key for the clusters file.

Note that, unlike Cardano where the pool hash serves as both the identifier and
the reward address, in Solana the identifier (vote account) and the reward
address (identity account) are distinct values. The vote account is used for
identifier and cluster lookup, while the identity account is used for address
lookup.

The vote account is chosen as the identifier because it is a stable, permanent
value, whereas a validator's identity account can be rotated over time. As a
result, the reliable attribution path is identifier lookup via the vote account:
validators that publish metadata are consistently grouped under their name. The
fallback path, which attributes a block to its identity account when no name is
known, is less robust, as a validator that rotates its identity account may
appear as more than one entity.

### Solana validator data preprocessing

The clusters file for Solana is generated from the identifiers file
(`identifiers/solana.json`), which contains the metadata (name and homepage)
that validators publish on-chain, keyed by vote account. No additional data
collection is required.

**Clusters** are built in the same way as for Cardano, by scoring every pair of
validators and merging those that score at or above a threshold. Since Solana
validators publish no ticker or description, scoring only uses the following
signals:

- Same homepage domain: +3
- Same name (after lowercasing and stripping trailing digits): +2

The default threshold is 3, so a homepage match alone is sufficient to cluster
two validators, while a name match alone is not and only serves as a
corroborating signal. Unlike Cardano, there is no penalty for different
domains, as with only two signals it would not change any outcome.

Homepages on shared path-style platforms (e.g. `x.com/<user>`,
`github.com/<user>`, `t.me/<user>`) are ignored, since the operator's identity
is in the URL path and all such homepages reduce to the same domain, which would
group unrelated validators together. Subdomain-style hosts (e.g. `*.github.io`,
`*.pages.dev`) are kept, since the subdomain identifies the operator.

Each cluster is named after the common prefix of its members' names when it is
a whole word, otherwise after the full name of the alphabetically first member.
