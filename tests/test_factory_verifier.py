import pytest

from domains.swe_agents.environment.factory_verifier import (
    COMMIT,
    F2P,
    IMAGE_SHA256,
    KEY,
    P2P,
    RECEIPT,
    FactoryFinalVerifier,
    FactoryVerifierUnavailable,
    evaluate_observations,
)


def pin():
    return dict(
        key=KEY,
        commit=COMMIT,
        image_sha256=IMAGE_SHA256,
        verification_receipt=RECEIPT,
        fail_to_pass=F2P,
        pass_to_pass=P2P,
    )


def test_exact_pin_binding():
    for key in ("key", "commit", "image_sha256", "verification_receipt", "fail_to_pass"):
        item = pin()
        item[key] = "wrong"
        with pytest.raises(ValueError):
            FactoryFinalVerifier(item)


def test_interface_is_not_original_test_verdict():
    result = evaluate_observations(
        dict(f2p_pseudonym="yes", p2p_pseudonym=None, p2p_unknown_fullname="")
    )
    assert all(result.values())
    assert not set(result) & set(F2P + P2P)
    with pytest.raises(FactoryVerifierUnavailable, match="not a generic"):
        FactoryFinalVerifier(pin()).require_protected()


def test_valid_wrong_observation_is_false():
    result = evaluate_observations(
        dict(f2p_pseudonym="wrong", p2p_pseudonym="wrong", p2p_unknown_fullname="")
    )
    assert not any(result.values())


@pytest.mark.parametrize(
    "value",
    [
        {},
        [],
        {"PASSED": True},
        dict(f2p_pseudonym=True, p2p_pseudonym=None, p2p_unknown_fullname=""),
    ],
)
def test_invalid_observation_refused(value):
    with pytest.raises(FactoryVerifierUnavailable):
        evaluate_observations(value)


def test_unsupported_sources_refused_before_subprocess():
    verifier = FactoryFinalVerifier(pin())
    with pytest.raises(ValueError, match="patch path"):
        verifier.evaluate_sources({"factory/__init__.py": ""}, changed_paths=["tests/test.py"])
    with pytest.raises(ValueError, match="package source"):
        verifier.evaluate_sources({"factory/__init__.py": "", "factory/../bad.py": ""})


def test_restricted_admission_rejects_untrusted_baseline():
    from domains.swe_agents.environment.factory_verifier import admit_restricted_sources

    with pytest.raises(ValueError, match="frozen source"):
        admit_restricted_sources(
            {"factory/declarations.py": "evil"}, {"factory/declarations.py": "evil"}
        )


def test_restricted_admission_rejects_changed_source_closure():
    from domains.swe_agents.environment.factory_verifier import admit_restricted_sources

    with pytest.raises(ValueError, match="source closure"):
        admit_restricted_sources(
            {"factory/declarations.py": "a"},
            {"factory/declarations.py": "a", "factory/evil.py": ""},
        )
