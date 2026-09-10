"""Explicit source notices that accompany redistributed derivatives."""

from pydantic import Field

from adversary.core.config import FrozenModel


class SourceNotice(FrozenModel):
    """A reviewed source address, licence text, and attribution; no inferred licence."""

    source: str = Field(min_length=1)
    revision: str = Field(min_length=1)
    spdx: str = Field(min_length=1)
    license_text: str = Field(min_length=1)
    attribution: str = Field(min_length=1)
    notice: str = ""

    @property
    def shippable(self) -> bool:
        return self.spdx in {"MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC", "0BSD"}
