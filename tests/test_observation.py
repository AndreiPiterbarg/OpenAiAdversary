"""Hostile observation programs must not escape the process boundary."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

from adversary.core.factors import Cell
from adversary.probe.observation import IsolatedObservation, ObservationError
from adversary.probe.program import ProgramKind, ProgramSource


def program(body, prepare="pass"):
    source = (
        "class P(Perturbation):\n"
        "    channel = Channel.OBSERVATION\n"
        "    clauses = ('rewrite',)\n"
        "    def prepare(self, session, spec):\n"
        f"        {prepare}\n"
        "    def observe(self, step, tool, args, result):\n"
        + "\n".join("        " + line for line in body.splitlines())
        + "\n"
    )
    return ProgramSource(kind=ProgramKind.PERTURBATION, source=source, entrypoint="P")


@unittest.skipUnless(sys.platform == "linux", "kernel confinement is Linux-only; checked on worker")
class ObservationKernelTests(unittest.TestCase):
    def start(self, body, *, active=True, prepare="pass", timeout=5):
        observer = IsolatedObservation(
            program(body, prepare),
            ("rewrite",),
            Cell(levels={"rewrite": "on" if active else "off"}),
            31,
            {"suffix": "adapted"},
            timeout=timeout,
        )
        self.addCleanup(observer.close)
        observer.prepare(None, {"visible": "task"})
        return observer

    def test_state_seed_and_config_survive_without_cross_episode_sharing(self):
        body = "self.n += 1\nreturn result + ':' + str(self.n) + ':' + str(self.rng.randint(1,999)) + self.config['suffix']"
        a = self.start(body, prepare="self.n = 0")
        b = self.start(body, prepare="self.n = 0")
        self.assertEqual(a.observe(1, "read", {}, "x"), b.observe(1, "read", {}, "x"))
        self.assertIn(":2:", a.observe(2, "read", {}, "x"))

    def test_file_read_and_write_are_blocked_by_kernel(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "secret"
            path.write_text("must not read")
            for expression in (f"open({str(path)!r}).read()", f"open({str(path)!r}, 'w')"):
                body = f"try:\n    {expression}\nexcept PermissionError:\n    return 'denied'\nreturn 'escaped'"
                worker = self.start(body)
                self.assertEqual(worker.observe(1, "read", {}, "x"), "denied")
            self.assertEqual(path.read_text(), "must not read")

    def test_network_and_process_creation_are_blocked(self):
        # ctypes is already loaded by the trusted confinement code. Even direct syscalls fail.
        for expression in ("ctypes.CDLL(None).socket(2, 1, 0)", "ctypes.CDLL(None).fork()"):
            worker = self.start(f"import ctypes\nreturn str({expression})")
            self.assertEqual(worker.observe(1, "read", {}, "x"), "-1")

    def test_host_credentials_are_not_inherited(self):
        previous = os.environ.get("PCODE_TEST_SECRET")
        os.environ["PCODE_TEST_SECRET"] = "never-in-worker"
        try:
            worker = self.start("import os\nreturn str(os.environ.get('PCODE_TEST_SECRET'))")
            self.assertEqual(worker.observe(1, "read", {}, "x"), "None")
        finally:
            if previous is None:
                os.environ.pop("PCODE_TEST_SECRET", None)
            else:
                os.environ["PCODE_TEST_SECRET"] = previous

    def test_inactive_program_cannot_change_observation(self):
        worker = self.start("return 'changed'", active=False)
        with self.assertRaises(ObservationError):
            worker.observe(1, "read", {}, "original")
        self.assertIsNotNone(worker._process.poll())

    def test_infinite_loop_times_out_and_worker_is_reaped(self):
        worker = self.start("while True: pass", timeout=1)
        with self.assertRaisesRegex(ObservationError, "timed out"):
            worker.observe(1, "read", {}, "x")
        self.assertIsNotNone(worker._process.poll())

    def test_invalid_or_flooded_output_is_rejected(self):
        for body in (
            "return 1",
            "return 'x' * 1_000_001",
            "print('not json', flush=True)\nreturn result",
        ):
            worker = self.start(body)
            with self.assertRaises(ObservationError):
                worker.observe(1, "read", {}, "x")

    def test_initialization_writes_are_also_denied(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "escaped"
            with self.assertRaises(ObservationError):
                self.start("return result", prepare=f"open({str(path)!r}, 'w')")
            self.assertFalse(path.exists())


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(ObservationKernelTests)
    )
    print(
        json.dumps(
            {
                "tests": result.testsRun,
                "failures": len(result.failures),
                "errors": len(result.errors),
                "skipped": len(result.skipped),
            }
        )
    )
    raise SystemExit(not result.wasSuccessful())


@unittest.skipUnless(sys.platform == 'linux', 'program confinement requires Linux')
class PureProgramKernelTests(unittest.TestCase):
    def test_generator_and_verifier_execute_confined(self):
        from adversary.core.trajectory import Trajectory
        from adversary.probe.executor import ConfinedPrograms

        executor = ConfinedPrograms()
        generator = ProgramSource(kind=ProgramKind.GENERATOR, entrypoint='G', source='''
class G(Generator):
    def __next__(self):
        seed = self.next_seed()
        return Instance(id=str(seed), cell=self.cell, seed=seed, spec=self.config['spec'],
                        oracle=self.config['oracle'], provenance=Provenance(
                            generator='G', generator_version='1', seed=seed))
''')
        config = {'spec': {'x': 1}, 'oracle': {'expected': 1}}
        a = executor.generate(generator, Cell(levels={}), 31, config, 2)
        b = executor.generate(generator, Cell(levels={}), 31, config, 2)
        self.assertEqual([i.id for i in a], [i.id for i in b])
        self.assertNotEqual(a[0].id, a[1].id)
        verifier = ProgramSource(kind=ProgramKind.VERIFIER, entrypoint='V', source='''
class V(Verifier):
    def verify(self, trajectory, oracle):
        return Verdict(passed=trajectory.final_state == oracle['expected'])
''')
        trace = Trajectory(instance_id='i', model_id='m', messages=(), final_state=1)
        self.assertTrue(executor.verify(verifier, trace, config['oracle']).passed)

    def test_generator_initialization_cannot_read_host_file(self):
        from adversary.execution.json_worker import WorkerError
        from adversary.probe.executor import ConfinedPrograms

        program = ProgramSource(kind=ProgramKind.GENERATOR, entrypoint='G', source='''
open('/etc/passwd').read()
class G(Generator):
    def __next__(self):
        return None
''')
        with self.assertRaises(WorkerError):
            ConfinedPrograms().generate(program, Cell(levels={}), 0, {}, 1)

    def test_generator_cannot_copy_hidden_oracle_into_configuration(self):
        from adversary.probe.executor import ConfinedPrograms
        from adversary.probe.program import ProgramKind, ProgramSource

        source = ProgramSource(kind=ProgramKind.GENERATOR, entrypoint='G', source='''
class G(Generator):
    def __next__(self):
        seed = self.next_seed()
        return Instance(id=str(seed), cell=self.cell, seed=seed,
                        spec=self.config['spec'], oracle=self.config['oracle'],
                        perturbation_config={'copy': self.config['oracle']},
                        provenance=Provenance(generator='G', generator_version='1', seed=seed))
''')
        result = ConfinedPrograms().generate(source, Cell(levels={}), 1,
            {'spec': {'task': 'private task data'}, 'oracle': {'answer': 'private answer'}}, 1)[0]
        self.assertEqual(result.oracle, {'answer': 'private answer'})
        self.assertNotIn('private answer', str(result.perturbation_config))
