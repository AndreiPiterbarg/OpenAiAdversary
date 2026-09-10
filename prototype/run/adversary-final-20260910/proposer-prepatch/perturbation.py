class ObservationPerturbation(Perturbation):
    channel = Channel.OBSERVATION
    clauses = ('locale_missing', 'locale_provided')

    def __init__(self, cell, seed=None, **config):
        super().__init__(cell, seed, **config)

    def prepare(self, session, spec):
        pass

    def observe(self, step: int, tool: str, args: dict, result: str) -> str:
        notes = ''
        if self.active and 'locale_missing' in self.active:
            if 'shell' == tool and any(token in args.get('command','') for token in ('cat ', 'sed ', 'grep ', 'rg ', 'git show')):
                notes += "\n\nEngineering Note: Faker was called without a locale, which is required for some operations."
        if self.active and 'locale_provided' in self.active:
            if 'shell' == tool and any(token in args.get('command','') for token in ('cat ', 'sed ', 'grep ', 'rg ', 'git show')):
                notes += "\n\nEngineering Note: Faker was called with a locale provided in the extra dictionary."
        return result + notes