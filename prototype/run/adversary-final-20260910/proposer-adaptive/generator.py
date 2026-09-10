class GeneratorWithClauses(Generator):
    def __init__(self, cell, seed=None, **config):
        super().__init__(cell, seed, **config)

    def next_seed(self) -> int:
        return self.rng.randint(0, 2**32)

    def __next__(self) -> Instance:
        instance = Instance(
            id=f"gen_{self.next_seed()}",
            cell=self.cell,
            seed=self.next_seed(),
            spec=self.config['spec'],
            oracle=self.config['oracle'],
            provenance=Provenance(
                generator='GeneratorWithClauses',
                generator_version='0',
                seed=self.next_seed(),
                source_license=self.config['source_license']
            ),
            resource=self.config['resource']
        )
        return instance