class TrajectoryVerifier(Verifier):
    version: str = '0'

    def verify(self, trajectory: Trajectory, oracle) -> Verdict:
        has_locale_error = False
        for msg in trajectory.messages:
            if hasattr(msg, 'content') and 'locale' in msg.content:
                has_locale_error = True
                break
        passed = not has_locale_error
        notes = ''
        if has_locale_error:
            notes = 'KeyError: locale detected in messages; Faker may have been called without a locale.'
        return Verdict(passed=passed, notes=notes)