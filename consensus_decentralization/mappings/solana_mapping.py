from consensus_decentralization.mappings.default_mapping import DefaultMapping


class SolanaMapping(DefaultMapping):
    """
    Mapping class tailored to Solana data. Inherits from DefaultMapping.

    Solana differs from the default (Bitcoin-style) mapping in two ways, both reflected in the overriden methods below:
        - the identifier is the producing validator's vote account, a unique and permanent value,
        so it is matched exactly rather than as a substring
        - each block has exactly one reward address, the validator's identity account, so there
        is no need to iterate over multiple addresses.

    Note that in Solana the identifier (vote account) and the reward address (identity account) are distinct values,
    unlike Cardano where the pool hash serves as both.
    """

    def __init__(self, project_name, output_dir, data_to_map):
        super().__init__(project_name, output_dir, data_to_map)

    def map_from_known_identifiers(self, block):
        """
        Maps one block to its block producer (validator) based on known identifiers.
        Overrides the map_from_known_identifiers of the DefaultMapping class to tailor
        the process to Solana, performing an exact lookup of the block's vote account
        rather than a substring search.
        :param block: dictionary with block information (block number, timestamp, identifiers, reward addresses)
        :returns: the name of the validator that produced the block, if it was successfully mapped, otherwise None
        """
        block_identifier = block['identifiers']
        if block_identifier in self.known_identifiers.keys():
            return self.known_identifiers[block_identifier]['name']
        return None

    def map_from_known_addresses(self, block):
        """
        Maps one block to its block producer (validator) based on known addresses.
        Overrides the map_from_known_addresses of the DefaultMapping class to tailor
        the process to Solana, taking advantage of the fact that each Solana block has
        exactly one reward address (the validator's identity account).
        :param block: dictionary with block information (block number, timestamp, identifiers, reward addresses)
        :returns: the name of the entity that produced the block, if it was successfully mapped, or
        '----- SPECIAL ADDRESS -----' if the reward address belongs to the "special addresses" of the project,
        otherwise None
        """
        reward_addresses = self.get_reward_addresses(block)
        if reward_addresses is None:  # there was no reward address associated with the block
            return None
        if len(reward_addresses) == 0:  # the reward address was deemed "special" and thus removed
            return '----- SPECIAL ADDRESS -----'
        reward_address = reward_addresses[0]
        if reward_address in self.known_addresses.keys():
            return self.known_addresses[reward_address]
        return None

    def map_from_known_clusters(self, block):
        """
        Maps one block to its block producer (validator cluster) based on known cluster information.
        Overrides the map_from_known_clusters of the DefaultMapping class to adapt the process to Solana.
        Specifically, the clusters file (clusters/solana.json) is keyed by VOTE ACCOUNT, i.e. the block's
        identifier, rather than by the reward address as in Cardano. This is because in Solana the vote
        account is the validator's stable, permanent identifier, whereas the reward (identity) address can
        be rotated.
        :param block: dictionary with block information (block number, timestamp, identifiers, reward addresses)
        :returns: string, which corresponds to the name of the cluster that produced the block, if it was
        successfully mapped, otherwise None
        """
        if len(self.known_clusters) > 0:
            block_identifier = block['identifiers']  # vote account
            if block_identifier in self.known_clusters.keys():
                return self.known_clusters[block_identifier]['cluster']
        return None
